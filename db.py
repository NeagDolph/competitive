from sqlalchemy import (
    create_engine, Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.sql import func
import json

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
    url = Column(Text, nullable=False)
    found_at = Column(DateTime(timezone=True), server_default=func.now())
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

    def get_or_create_domain(self, name: str, session: Session | None = None) -> Domain:
        """
        Retrieve a domain by name, or prepare it for creation if it does not exist.
        If called without an active session, a new session is created and committed.
        If called with an active session, the object is added/retrieved, flushed (to assign IDs),
        but the final commit is left to the caller.
        """
        managed_session = session is None
        # Use provided session or create a new one if None was passed.
        s = session if session else self.Session()

        try:
            domain = s.query(Domain).filter_by(name=name).first()
            if not domain:
                domain = Domain(name=name)
                s.add(domain)
                # Flush ensures the new domain gets an ID and is queryable within this transaction,
                # but doesn't finalize the transaction like commit().
                s.flush()
                # Only commit if we created the session specifically for this call.
                if managed_session:
                    s.commit()
            return domain
        except Exception:
            # If we created the session, we should roll back on error.
            if managed_session:
                s.rollback()
            raise # Re-raise the exception for the caller to handle
        finally:
            # If we created the session, we must close it.
            if managed_session:
                s.close()

    def add_category_link(self, domain_name: str, url: str) -> CategoryLink:
        """
        Add a category link for a given domain name and URL, or retrieve it if it already exists.
        """
        with self.Session() as session:
            domain = self.get_or_create_domain(domain_name, session)
            link = session.query(CategoryLink).filter_by(url=url, domain_id=domain.id).first()
            if not link:
                link = CategoryLink(url=url, domain_id=domain.id)
                session.add(link)
                session.commit()
            return link
        
    def add_category_links(self, domain_name: str, urls: list[str]) -> list:
        """
        Add multiple category links for a given domain name and list of URLs.
        Returns a list of CategoryLink objects.
        """
        links = []
        for url in urls:
            link = self.add_category_link(domain_name, url)
            links.append(link)
        return links
        
    def get_category_links(self, domain_name):
        """
        Retrieve all category links for a given domain name.
        """
        with self.Session() as session:
            domain = session.query(Domain).filter_by(name=domain_name).first()
            if not domain:
                return []
            
            return session.query(CategoryLink).filter_by(domain_id=domain.id).all()

    def add_product(self, category_link_id, name, price, original_price=None, discount=None, image_url=None, url=None):
        """
        Add a product to the database with the given details and link it to a category link and domain.
        """
        with self.Session() as session:
            product = Product(
                name=name,
                price=price,
                original_price=original_price,
                discount=discount,
                image_url=image_url,
                url=url,
                category_link_id=category_link_id
            )
            session.add(product)
            session.commit()
            return product

    def add_schema(self, domain_name, schema_json):
        """
        Add a product schema for a given domain name.
        """
        with self.Session() as session:
            domain = self.get_or_create_domain(domain_name)
            schema = ProductSchema(domain_id=domain.id, schema_json=json.dumps(schema_json))
            session.add(schema)
            session.commit()
            return schema

    def get_latest_schema(self, domain_name):
        """
        Retrieve the latest product schema for a given domain name.
        """
        with self.Session() as session:
            domain = session.query(Domain).filter_by(name=domain_name).first()
            if not domain:
                return None
            return (
                session.query(ProductSchema)
                .filter_by(domain_id=domain.id)
                .order_by(ProductSchema.generated_at.desc())
                .first()
            )

    def add_products(self, domain_name, category_url, products):
        """
        Add multiple products to the database, linking them to the specified domain name and category URL.
        Each product should have at least 'name' and 'price'. Optional fields: 'original_price', 'discount', 'image_url', 'url'.
        """
        with self.Session() as session:
            domain = self.get_or_create_domain(domain_name)
            link = session.query(CategoryLink).filter_by(url=category_url, domain_id=domain.id).first()
            if not link:
                link = CategoryLink(url=category_url, domain_id=domain.id)
                session.add(link)
                session.commit()
            for p in products:
                self.add_product(
                    link.id,
                    p.get('name'),
                    p.get('price'),
                    p.get('original_price'),
                    p.get('discount'),
                    p.get('image_url'),
                    p.get('url')
                ) 