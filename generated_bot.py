import os
import re
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    
    # Setup user data directory for persistence
    state_file = "user_data/state.json"
    os.makedirs("user_data", exist_ok=True)
    
    # Check for existing login state
    if os.path.exists(state_file):
        context = browser.new_context(storage_state=state_file)
        print("✅ Loaded saved login state")
    else:
        context = browser.new_context()
        print("⚠️ No saved login state found")
    
    page = context.new_page()
    page.goto("https://www.xiaohongshu.com/explore")
    
    # Manual login if no saved state
    if not os.path.exists(state_file):
        print("⏳ Please complete login manually...")
        input("Press Enter after you've logged in successfully: ")
        
        # Save login state for future use
        context.storage_state(path=state_file)
        print("✅ Login state saved to user_data/state.json")
    
    print("✅ Login completed, starting to browse notes...")
    
    # Browse first note
    print("📝 Clicking first note...")
    page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(1).click()
    page.wait_for_timeout(2000)  # Wait for note to load
    
    # Interact with first note (original recorded actions)
    page.locator("div").filter(has_text="随便变关注 00:002x1.5x1x0.75x0.5x").first.click()
    page.locator("div").filter(has_text="随便变关注 00:002x1.5x1x0.75x0.5x").first.click()
    page.locator("body").press("Escape")
    page.wait_for_timeout(1000)
    
    # Browse second note
    print("📝 Clicking second note...")
    page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(2).click()
    page.wait_for_timeout(2000)
    page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(2).press("Escape")
    page.wait_for_timeout(1000)
    
    # Browse third note
    print("📝 Clicking third note...")
    page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(3).click()
    page.wait_for_timeout(2000)
    page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(3).press("Escape")
    page.wait_for_timeout(1000)
    
    print("✅ Successfully browsed first three notes!")
    print("⏳ Keeping browser open for 10 seconds...")
    page.wait_for_timeout(10000)
    
    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)