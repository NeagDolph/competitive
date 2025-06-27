import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import threading
from pathlib import Path
from typing import List, Optional, Callable
import sys
import os

# Add parent directory to path to import from main project
sys.path.append(str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright, Browser, Page
from data_manager import PLPDataManager
from util.clean_html import clean_html


class PLPLabelerGUI:
    """
    GUI application for labeling PLP pages using Playwright for rendering and tkinter for the interface.
    """
    
    def __init__(self, urls: List[str], data_manager: PLPDataManager):
        self.urls = urls
        self.data_manager = data_manager
        self.current_index = 0
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Create GUI
        self.root = tk.Tk()
        self.root.title("PLP Labeling Tool")
        self.root.geometry("1200x800")
        
        # Variables
        self.current_url = tk.StringVar()
        self.progress_text = tk.StringVar()
        self.html_content = ""
        self.cleaned_html = ""
        
        self.setup_gui()
        self.update_progress()
        
        # Start browser in background
        self.start_browser()
    
    def setup_gui(self):
        """Setup the GUI layout."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Progress info
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(progress_frame, textvariable=self.progress_text, font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        
        # URL display
        url_frame = ttk.Frame(main_frame)
        url_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(url_frame, text="Current URL:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Label(url_frame, textvariable=self.current_url, font=('Arial', 10), foreground='blue').pack(side=tk.LEFT, padx=(10, 0))
        
        # Screenshot/preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Page Preview", padding="5")
        preview_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        # Text preview
        self.preview_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=20)
        self.preview_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Control buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        
        # Load page button
        self.load_btn = ttk.Button(button_frame, text="Load Page", command=self.load_current_page)
        self.load_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Labeling buttons
        label_frame = ttk.LabelFrame(button_frame, text="Is this a Product Listing Page (PLP)?", padding="10")
        label_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        self.plp_yes_btn = ttk.Button(label_frame, text="1 - YES (PLP)", command=lambda: self.label_page(1))
        self.plp_yes_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.plp_no_btn = ttk.Button(label_frame, text="0 - NO (Not PLP)", command=lambda: self.label_page(0))
        self.plp_no_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Navigation buttons
        nav_frame = ttk.Frame(button_frame)
        nav_frame.pack(side=tk.RIGHT, padx=(10, 0))
        
        self.prev_btn = ttk.Button(nav_frame, text="Previous", command=self.previous_page)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.next_btn = ttk.Button(nav_frame, text="Next", command=self.next_page)
        self.next_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Skip button
        self.skip_btn = ttk.Button(nav_frame, text="Skip", command=self.skip_page)
        self.skip_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready to load pages...")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Bind keyboard shortcuts
        self.root.bind('<Key-0>', lambda e: self.label_page(0))
        self.root.bind('<Key-1>', lambda e: self.label_page(1))
        self.root.bind('<Left>', lambda e: self.previous_page())
        self.root.bind('<Right>', lambda e: self.next_page())
        self.root.bind('<space>', lambda e: self.skip_page())
        self.root.bind('<Return>', lambda e: self.load_current_page())
        
        # Focus on root to capture key events
        self.root.focus_set()
    
    def start_browser(self):
        """Start Playwright browser in a separate thread."""
        def run_browser():
            asyncio.run(self._init_browser())
        
        self.browser_thread = threading.Thread(target=run_browser, daemon=True)
        self.browser_thread.start()
    
    async def _init_browser(self):
        """Initialize Playwright browser."""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=False)
            self.page = await self.browser.new_page()
            
            # Configure page
            await self.page.set_viewport_size({"width": 1200, "height": 800})
            
            self.root.after(0, lambda: self.status_var.set("Browser ready. Click 'Load Page' to start."))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"Browser error: {str(e)}"))
    
    def update_progress(self):
        """Update progress display."""
        total = len(self.urls)
        current = self.current_index + 1
        self.progress_text.set(f"Page {current} of {total}")
        
        if self.current_index < len(self.urls):
            self.current_url.set(self.urls[self.current_index])
        else:
            self.current_url.set("No more URLs")
    
    def load_current_page(self):
        """Load the current page in the browser."""
        if self.current_index >= len(self.urls):
            messagebox.showinfo("Complete", "All URLs have been processed!")
            return
        
        if not self.page:
            self.status_var.set("Browser not ready yet...")
            return
        
        url = self.urls[self.current_index]
        self.status_var.set(f"Loading {url}...")
        
        # Load page in browser thread
        def load_page():
            asyncio.run(self._load_page_async(url))
        
        threading.Thread(target=load_page, daemon=True).start()
    
    async def _load_page_async(self, url: str):
        """Load page asynchronously."""
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Get HTML content
            self.html_content = await self.page.content()
            
            # Clean HTML
            try:
                self.cleaned_html = clean_html(self.html_content)
            except Exception as e:
                print(f"Error cleaning HTML: {e}")
                self.cleaned_html = self.html_content
            
            # Update preview in main thread
            preview_text = f"URL: {url}\n\n"
            preview_text += f"HTML Length: {len(self.html_content)} characters\n"
            preview_text += f"Cleaned HTML Length: {len(self.cleaned_html)} characters\n\n"
            preview_text += "=== Page Title and Meta ===\n"
            preview_text += f"Title: {await self.page.title()}\n\n"
            preview_text += "=== Cleaned HTML Preview (first 2000 chars) ===\n"
            preview_text += self.cleaned_html[:2000] + ("..." if len(self.cleaned_html) > 2000 else "")
            
            self.root.after(0, lambda: self._update_preview(preview_text))
            self.root.after(0, lambda: self.status_var.set("Page loaded. Please label: 0 (Not PLP) or 1 (PLP)"))
            
        except Exception as e:
            error_msg = f"Error loading page: {str(e)}"
            self.root.after(0, lambda: self.status_var.set(error_msg))
            self.root.after(0, lambda: self._update_preview(f"Error loading {url}:\n{error_msg}"))
    
    def _update_preview(self, text: str):
        """Update the preview text widget."""
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(1.0, text)
    
    def label_page(self, label: int):
        """Label the current page."""
        if not self.html_content:
            messagebox.showwarning("Warning", "Please load the page first!")
            return
        
        url = self.urls[self.current_index]
        
        # Save the labeled data
        def save_data():
            asyncio.run(self._save_label_async(url, label))
        
        threading.Thread(target=save_data, daemon=True).start()
    
    async def _save_label_async(self, url: str, label: int):
        """Save the label asynchronously."""
        try:
            success = await self.data_manager.save_sample(
                url=url,
                html_content=self.html_content,
                is_plp=label,
                cleaned_html=self.cleaned_html if self.cleaned_html != self.html_content else None
            )
            
            if success:
                label_text = "PLP" if label == 1 else "Not PLP"
                self.root.after(0, lambda: self.status_var.set(f"Saved: {label_text}"))
                self.root.after(0, self.next_page)
            else:
                self.root.after(0, lambda: self.status_var.set("Duplicate content - skipped"))
                self.root.after(0, self.next_page)
                
        except Exception as e:
            error_msg = f"Error saving label: {str(e)}"
            self.root.after(0, lambda: self.status_var.set(error_msg))
    
    def next_page(self):
        """Move to the next page."""
        if self.current_index < len(self.urls) - 1:
            self.current_index += 1
            self.update_progress()
            self.html_content = ""
            self.cleaned_html = ""
            self._update_preview("Click 'Load Page' to load the next URL")
        else:
            messagebox.showinfo("Complete", "You have reached the end of the URLs!")
            self.show_stats()
    
    def previous_page(self):
        """Move to the previous page."""
        if self.current_index > 0:
            self.current_index -= 1
            self.update_progress()
            self.html_content = ""
            self.cleaned_html = ""
            self._update_preview("Click 'Load Page' to load the previous URL")
    
    def skip_page(self):
        """Skip the current page without labeling."""
        self.next_page()
    
    def show_stats(self):
        """Show current dataset statistics."""
        stats = self.data_manager.get_dataset_stats()
        stats_text = f"""Dataset Statistics:
        
Total Samples: {stats['total_samples']}
PLP Samples: {stats['plp_samples']}
Non-PLP Samples: {stats['non_plp_samples']}
Balance Ratio: {stats['balance_ratio']:.2%}

Domains:
{chr(10).join([f"  {domain}: {count}" for domain, count in stats['domains'].items()])}
        """
        messagebox.showinfo("Dataset Statistics", stats_text)
    
    def run(self):
        """Start the GUI application."""
        try:
            self.root.mainloop()
        finally:
            # Cleanup
            if self.browser:
                asyncio.run(self.browser.close())
            if self.playwright:
                asyncio.run(self.playwright.stop())


async def main():
    """Main function to run the labeling tool."""
    # Example usage - you can modify this to load URLs from your database
    urls = [
        "https://example.com/category1",
        "https://example.com/category2",
        # Add more URLs here
    ]
    
    data_manager = PLPDataManager("plp_data")
    
    if not urls:
        print("No URLs provided. Please add URLs to the list in the main() function.")
        return
    
    gui = PLPLabelerGUI(urls, data_manager)
    gui.run()


if __name__ == "__main__":
    asyncio.run(main()) 