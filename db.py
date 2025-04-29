from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.sql import func
import json
from datetime import datetime, timezone

from util.types import Link

Base = declarative_base()

class Domain(Base):
    __tablename__ = 'domains'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    category_links = relationship('CategoryLink', back_populates='domain')
    schemas = relationship('ProductSchema', back_populates='domain')

class CategoryLink(Base):
    __tablename__ = 'category_links'
    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False, unique=True)
    found_at = Column(DateTime(timezone=True), server_default=func.now())
    link_html = Column(Text, nullable=True)
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    domain_id = Column(Integer, ForeignKey('domains.id'), nullable=False)
    domain = relationship('Domain', back_populates='category_links')
    products = relationship('Product', back_populates='category_link')
    __table_args__ = (UniqueConstraint('url', 'domain_id', name='_url_domain_uc'),)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(String, nullable=False)
    original_price = Column(String, nullable=True)
    discount = Column(String, nullable=True)
    image_url = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    category_link_id = Column(Integer, ForeignKey('category_links.id'), nullable=False)
    domain_id = Column(Integer, ForeignKey('domains.id'), nullable=False)
    category_link = relationship('CategoryLink', back_populates='products')
    domain = relationship('Domain')
    found_at = Column(DateTime(timezone=True), server_default=func.now())

class ProductSchema(Base):
    __tablename__ = 'product_schemas'
    id = Column(Integer, primary_key=True)
    domain_id = Column(Integer, ForeignKey('domains.id'), nullable=False)
    schema_json = Column(Text, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    domain = relationship('Domain', back_populates='schemas')

class DB:
    def __init__(self, db_path='sqlite:///crawler_data.db'):
        """
        Initialize the database connection and create tables if they do not exist.
        """
        self.engine = create_engine(db_path, echo=False, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

    def get_or_create_domain(self, name: str, session: Session | None = None) -> Domain | None:
        """
        Ensure a domain exists in the database by name. No return value.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            domain = s.query(Domain).filter_by(name=name).first()
            if not domain:
                domain = Domain(name=name)
                s.add(domain)
                s.flush()
                if managed_session:
                    s.commit()

            return domain
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def add_category_link(self, domain_name: str, url: str, link_html: str, session: Session | None = None) -> None:
        """
        Add a category link for a given domain name and URL, or ensure it exists. No return value.
        If the URL already exists for any domain, it will not be added again.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            # First check if the URL exists for any domain
            existing_link = s.query(CategoryLink).filter_by(url=url).first()
            if existing_link:
                return  # URL already exists, don't add it again
            
            domain = self.get_or_create_domain(domain_name, s)
            link = CategoryLink(url=url, domain_id=domain.id, link_html=link_html)
            s.add(link)
            s.flush()
            if managed_session:
                s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise
        finally:
            if managed_session:
                s.close()

    def add_category_links(self, domain_name: str, urls: list[Link], session: Session | None = None) -> None:
        """
        Add multiple category links for a given domain name and list of URLs. No return value.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            for url in urls:
                self.add_category_link(domain_name, url["href"], url["html"], s)
            if managed_session:
                s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def get_category_links(self, domain_name: str, session: Session | None = None) -> list[str]:
        """
        Retrieve all category link URLs for a given domain name.
        Returns a list of URLs.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            domain = self.get_or_create_domain(domain_name, s)
            if not domain:
                return []
            links = s.query(CategoryLink).filter_by(domain_id=domain.id).all()
            return [cl.url for cl in links]
        except Exception:
            if managed_session:
                s.rollback()
            raise
        finally:
            if managed_session:
                s.close()

    def add_product(self, domain_name, category_url, name, price, original_price=None, discount=None, image_url=None, url=None, session: Session | None = None) -> None:
        """
        Add a product to the database with the given details and link it to a category link and domain. No return value.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            self.get_or_create_domain(domain_name, s)
            domain = s.query(Domain).filter_by(name=domain_name).first()
            link = s.query(CategoryLink).filter_by(url=category_url, domain_id=domain.id).first()
            if not link:    
                link = CategoryLink(url=category_url, domain_id=domain.id)
                s.add(link)
                s.flush()
                if managed_session:
                    s.commit()
            product = Product(
                name=name,
                price=price,
                original_price=original_price,
                discount=discount,
                image_url=image_url,
                url=url,
                category_link_id=link.id,
                domain_id=domain.id
            )
            s.add(product)
            s.flush()
            if managed_session:
                s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def add_schema(self, domain_name, schema_json, session: Session | None = None) -> None:
        """
        Add a product schema for a given domain name. No return value.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            self.get_or_create_domain(domain_name, s)
            domain = s.query(Domain).filter_by(name=domain_name).first()
            schema = ProductSchema(domain_id=domain.id, schema_json=json.dumps(schema_json))
            s.add(schema)
            s.flush()
            if managed_session:
                s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def get_latest_schema(self, domain_name, session: Session | None = None) -> dict | None:
        """
        Retrieve the latest product schema for a given domain name.
        Returns the schema JSON as a dict, or None if not found.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            domain = s.query(Domain).filter_by(name=domain_name).first()
            if not domain:
                return None
            schema_obj = (
                s.query(ProductSchema)
                .filter_by(domain_id=domain.id)
                .order_by(ProductSchema.generated_at.desc())
                .first()
            )
            if schema_obj:
                return {
                    "schema": json.loads(schema_obj.schema_json),
                    "generated_at": schema_obj.generated_at
                }
            return None
        except Exception:
            if managed_session:
                s.rollback()
            raise
        finally:
            if managed_session:
                s.close()

    def add_products(self, domain_name, category_url, products, session: Session | None = None) -> None:
        """
        Add multiple products to the database, linking them to the specified domain name and category URL.
        Each product should have at least 'name' and 'price'. Optional fields: 'original_price', 'discount', 'image_url', 'url'.
        No return value.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            self.get_or_create_domain(domain_name, s)
            domain = s.query(Domain).filter_by(name=domain_name).first()
            link = s.query(CategoryLink).filter_by(url=category_url, domain_id=domain.id).first()
            if not link:
                link = CategoryLink(url=category_url, domain_id=domain.id)
                s.add(link)
                s.flush()
                if managed_session:
                    s.commit()
            for p in products:
                product = Product(
                    name=p.get('name'),
                    price=p.get('price'),
                    original_price=p.get('original_price'),
                    discount=p.get('discount'),
                    image_url=p.get('image_url'),
                    url=p.get('url'),
                    category_link_id=link.id,
                    domain_id=domain.id
                )
                s.add(product)
            if managed_session:
                s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def update_category_link_crawled(self, domain_name, category_url, session: Session | None = None) -> None:
        """
        Update the last_crawled_at field for a CategoryLink to the current time, using domain name and category URL.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            domain = self.get_or_create_domain(domain_name, s)
            if not domain:
                return
            link = s.query(CategoryLink).filter_by(url=category_url, domain_id=domain.id).first()
            if link:
                link.last_crawled_at = datetime.now(timezone.utc)
                if managed_session:
                    s.commit()
        except Exception:
            if managed_session:
                s.rollback()
            raise

    def get_oldest_uncrawled_category_link(self, domain_name, session: Session | None = None) -> str | None:
        """
        Retrieve the URL of the CategoryLink for the given domain that hasn't been crawled in the longest period.
        Returns the URL string or None if none exist.
        """
        managed_session = session is None
        s = session if session else self.Session()
        try:
            domain = s.query(Domain).filter_by(name=domain_name).first()
            if not domain:
                return None
            link = (
                s.query(CategoryLink)
                .filter_by(domain_id=domain.id)
                .order_by(CategoryLink.last_crawled_at.asc().nullsfirst(), CategoryLink.found_at.asc())
                .first()
            )
            if link:
                return link.url
            return None 
        except Exception:
            if managed_session:
                s.rollback()
            raise
        finally:
            if managed_session:
                s.close()