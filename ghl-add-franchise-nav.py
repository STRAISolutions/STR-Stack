#!/usr/bin/env python3
"""
Add "Franchise" navigation link to STR Solutions USA website in GHL.
Injects a JS snippet into the website's trackingCodeHead that dynamically
adds a "Franchise" nav item to the header menu.
"""
import requests
import json
import sys

API_BASE = "https://services.leadconnectorhq.com"
HEADERS = {
    "Authorization": "Bearer pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7",
    "Version": "2021-07-28",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

LOCATION_ID = "1OOZ4AKIgxO8QKKMnIcK"
WEBSITE_FUNNEL_ID = "qGalpqsKZWaqcDoruCnR"  # STR Solutions USA website

# JS snippet that adds "Franchise" to the site navigation
NAV_INJECT_SCRIPT = """
<!-- Franchise Nav Injection -->
<script>
(function() {
  function addFranchiseNav() {
    // Find the navigation menu container (GHL uses various selectors)
    var navSelectors = [
      '.hl_page-header nav ul',
      '.hl_page-header .menu ul',
      'header nav ul',
      'header .nav-menu ul',
      '.header-section nav ul',
      '[data-page-element="Header"] nav ul',
      '.nav-links',
      '.menu-items'
    ];
    var navList = null;
    for (var i = 0; i < navSelectors.length; i++) {
      navList = document.querySelector(navSelectors[i]);
      if (navList) break;
    }
    if (!navList) {
      // Try broader search for any nav with links
      var allNavs = document.querySelectorAll('nav ul, .navigation ul, header ul');
      for (var j = 0; j < allNavs.length; j++) {
        if (allNavs[j].children.length > 2) {
          navList = allNavs[j];
          break;
        }
      }
    }
    if (!navList) return false;

    // Check if Franchise link already exists
    var existing = navList.querySelectorAll('a');
    for (var k = 0; k < existing.length; k++) {
      if (existing[k].textContent.trim().toLowerCase() === 'franchise' ||
          existing[k].textContent.trim().toLowerCase() === 'franchises') {
        return true; // Already exists
      }
    }

    // Clone the style from an existing nav item
    var lastItem = navList.lastElementChild;
    if (!lastItem) return false;
    var newItem = lastItem.cloneNode(true);
    var newLink = newItem.querySelector('a');
    if (newLink) {
      newLink.textContent = 'Franchise';
      newLink.href = '/franchise';
      newLink.setAttribute('data-href', '/franchise');
      newLink.removeAttribute('data-page-element');
    } else {
      // Create link from scratch
      newItem.innerHTML = '';
      var a = document.createElement('a');
      a.href = '/franchise';
      a.textContent = 'Franchise';
      a.style.cssText = lastItem.querySelector('a') ?
        lastItem.querySelector('a').style.cssText : '';
      newItem.appendChild(a);
    }

    // Insert before the last few utility items (Privacy, Terms, etc.)
    // Find Pricing or Owner Portal to insert after
    var insertAfter = null;
    var items = navList.children;
    for (var m = 0; m < items.length; m++) {
      var link = items[m].querySelector('a');
      if (link) {
        var txt = link.textContent.trim().toLowerCase();
        if (txt === 'pricing' || txt === 'owner portal') {
          insertAfter = items[m];
        }
      }
    }

    if (insertAfter && insertAfter.nextSibling) {
      navList.insertBefore(newItem, insertAfter.nextSibling);
    } else {
      navList.appendChild(newItem);
    }
    return true;
  }

  // Run on DOM ready and after GHL hydration
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(addFranchiseNav, 500);
      setTimeout(addFranchiseNav, 1500);
    });
  } else {
    setTimeout(addFranchiseNav, 500);
    setTimeout(addFranchiseNav, 1500);
  }

  // Also observe for dynamic nav loading
  var observer = new MutationObserver(function(mutations) {
    if (addFranchiseNav()) {
      observer.disconnect();
    }
  });
  observer.observe(document.body || document.documentElement, {
    childList: true, subtree: true
  });
  // Auto-disconnect after 10s
  setTimeout(function() { observer.disconnect(); }, 10000);
})();
</script>
"""


def get_current_funnel():
    """Fetch current website funnel data."""
    r = requests.get(
        f"{API_BASE}/funnels/funnel/list",
        params={"locationId": LOCATION_ID},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    for f in data.get("funnels", []):
        if f["_id"] == WEBSITE_FUNNEL_ID:
            return f
    return None


def update_tracking_code(funnel):
    """Update the website's trackingCodeHead to include the nav injection script."""
    current_head = funnel.get("trackingCodeHead", "") or ""

    # Check if already injected
    if "Franchise Nav Injection" in current_head:
        print("  Nav injection script already present in trackingCodeHead.")
        print("  To re-inject, manually remove the old script first.")
        return False

    new_head = current_head + NAV_INJECT_SCRIPT

    payload = {
        "trackingCodeHead": new_head,
    }

    r = requests.put(
        f"{API_BASE}/funnels/funnel/{WEBSITE_FUNNEL_ID}",
        json=payload,
        headers=HEADERS,
        timeout=15,
    )

    if r.status_code in (200, 201):
        print("  + trackingCodeHead updated with Franchise nav injection script.")
        return True
    else:
        print(f"  PUT funnel update failed ({r.status_code}): {r.text[:300]}")
        # Fallback: try via funnel steps
        return False


def verify_franchise_step(funnel):
    """Verify the franchise page step exists."""
    steps = funnel.get("steps", [])
    for s in steps:
        if s.get("url") == "/franchise":
            print(f"  + Franchise page confirmed: step '{s['name']}' at /franchise")
            print(f"    Page ID: {s['pages'][0] if s.get('pages') else '?'}")
            print(f"    Sequence: {s.get('sequence')}")
            return True
    print("  ! Franchise page step NOT found in website.")
    return False


def main():
    mode = "--execute" if len(sys.argv) > 1 and sys.argv[1] == "--execute" else "--dry-run"

    print("=" * 60)
    print("GHL Franchise Nav Injection Script")
    print(f"Mode: {mode}")
    print("=" * 60)

    print("\n1. Fetching website funnel data...")
    funnel = get_current_funnel()
    if not funnel:
        print("  ERROR: Website funnel not found!")
        return

    print(f"  Found: {funnel['name']} (ID: {funnel['_id']})")
    print(f"  Steps: {len(funnel.get('steps', []))}")
    print(f"  Current trackingCodeHead: {'[empty]' if not funnel.get('trackingCodeHead') else f'[{len(funnel.get('trackingCodeHead', ''))} chars]'}")

    print("\n2. Verifying franchise page step...")
    verify_franchise_step(funnel)

    if mode == "--dry-run":
        print("\n3. DRY RUN — Would inject this into trackingCodeHead:")
        print("-" * 40)
        print(NAV_INJECT_SCRIPT[:200] + "...")
        print("-" * 40)
        print("\nRun with --execute to apply.")
    else:
        print("\n3. Injecting nav script into trackingCodeHead...")
        success = update_tracking_code(funnel)
        if success:
            print("\n  DONE. The 'Franchise' link will now appear in the site navigation.")
            print("  Clear your browser cache and reload strsolutionsusa.com to see it.")
        else:
            print("\n  Script injection via API may not be supported.")
            print("  FALLBACK: Paste this into GHL > Sites > STR Solutions USA > Settings > Tracking Code (Head):")
            print("-" * 40)
            print(NAV_INJECT_SCRIPT)
            print("-" * 40)

    print("\nDone.")


if __name__ == "__main__":
    main()
