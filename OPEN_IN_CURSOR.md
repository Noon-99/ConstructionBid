# Open Archonix in Cursor

## Servers Running ✅
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## View Project dcfd6ded

**Direct Link:**
http://localhost:3000/projects/dcfd6ded

## How to Open in Cursor

1. **Option 1: Command Palette**
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type "Simple Browser" or "Preview"
   - Enter URL: `http://localhost:3000/projects/dcfd6ded`

2. **Option 2: Right-click in Cursor**
   - Right-click on this file
   - Look for "Open in Browser" or "Preview" option

3. **Option 3: Use Cursor's Web View**
   - In Cursor, go to View → Command Palette
   - Search for "Simple Browser: Show"
   - Paste: `http://localhost:3000/projects/dcfd6ded`

## What to Check

Once you have the project open, verify:

1. **Overview Tab**
   - Look for "Compliance & Procurement" panel
   - Should show government project detection
   - Should show compliance flags

2. **Bid Tab**
   - Look for "Download Excel Export" button
   - Check line items for "Performance & Payment Bonds"
   - Check line items for "Supplemental Insurance"
   - Check line items for "Contingency"

3. **Review Tab**
   - Look for "Compliance Adjustments Applied" card
   - Should show compliance adjustment explanations

4. **Check Total Cost**
   - Should be higher than base scope if compliance costs applied
   - For government projects, expect ~$50k-100k in compliance adders

## Debug Info

If compliance detection didn't work:
- Check browser console for errors
- Check backend logs for procurement analyzer messages
- Run: `python backend/scripts/verify_compliance_detection.py dcfd6ded`
