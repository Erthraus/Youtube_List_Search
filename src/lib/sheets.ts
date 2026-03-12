import { google } from "googleapis";

const getSheetsClient = (accessToken: string) => {
  const auth = new google.auth.OAuth2();
  auth.setCredentials({ access_token: accessToken });
  return google.sheets({ version: "v4", auth });
};

export async function createSheetIfNotExists(accessToken: string, title: string): Promise<string> {
  try {
    const auth = new google.auth.OAuth2();
    auth.setCredentials({ access_token: accessToken });
    const sheets = google.sheets({ version: "v4", auth });
    const drive = google.drive({ version: 'v3', auth });
    
    // Try to find if the sheet exists in the user's drive
    const fileParams = { q: `name='${title}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false` };
    const res = await drive.files.list(fileParams);
    
    if (res.data.files && res.data.files.length > 0) {
      return res.data.files[0].id!;
    }
    
    // Create it
    const newSheet = await sheets.spreadsheets.create({
      requestBody: {
        properties: { title }
      }
    });
    
    return newSheet.data.spreadsheetId!;
  } catch (error) {
    console.warn("Google Drive/Sheets API Error (possibly not enabled in GCP). Bypassing cloud save.", error);
    return ""; // Return empty string to signify no sheet available
  }
}

// Map from Video ID to Custom Category
export async function loadTagsFromSheet(accessToken: string, spreadsheetId: string): Promise<Record<string, string>> {
  if (!spreadsheetId) return {};
  
  const sheets = getSheetsClient(accessToken);
  try {
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId,
      range: "A:C", // A: Video ID, B: Title, C: Category — no sheet name prefix, uses first sheet regardless of language
    });
    
    const rows = res.data.values;
    if (!rows || rows.length === 0) return {};
    
    const map: Record<string, string> = {};
    // Skip header
    for (let i = 1; i < rows.length; i++) {
      const [id, _title, category] = rows[i];
      if (id && category) {
        map[id] = category;
      }
    }
    return map;
  } catch (err) {
    console.error("Error loading tags from sheet:", err);
    return {};
  }
}

export async function saveTagsToSheet(accessToken: string, spreadsheetId: string, updates: Record<string, {title: string, category: string}>) {
  if (!spreadsheetId) return;
  
  const sheets = getSheetsClient(accessToken);
  // We rewrite the entire sheet for simplicity as the application loads everything into memory anyway
  // Setup Header
  const values = [["Video ID", "Title", "AI Category"]];
  for (const [id, data] of Object.entries(updates)) {
    if (data.category !== "General / Unrelated") {
      values.push([id, data.title, data.category]);
    }
  }
  
  await sheets.spreadsheets.values.update({
    spreadsheetId,
    range: "A1", // No sheet name prefix — works regardless of account language (Sheet1, Sayfa1, etc.)
    valueInputOption: "USER_ENTERED",
    requestBody: { values }
  });
  
  // Also clear whatever rest of the rows if it got smaller
  // In a real database this isn't needed, but for sheets it's recommended to do a clear and update, or just overwrite padding
}
