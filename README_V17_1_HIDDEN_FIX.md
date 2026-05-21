# Avalon v17.1 Hidden Fix

Fixes the deployment issue where opening the root URL immediately displayed the identity card overlay.

Cause: `static/style.css` did not define a global `.hidden { display:none }` utility, so elements such as `joinView`, `gameView`, `dealOverlay`, and modal sheets were visible even though the HTML marked them as hidden.

Change: Added global `.hidden { display: none !important; }`.
