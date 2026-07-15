import { useState } from "react";

// Always call the backend same-origin via relative /api paths. In production the
// ingress routes /api to the backend; in local dev the Vite proxy (vite.config.js)
// forwards /api to the backend on :8000. Never hardcode an absolute API URL.

const DEFAULT_FIELDS = {
  address_column: "address",
  postcode_column: "postcode",
  tracking_column: "tracking_id",
  type_value: "PE",
  sub_type_value: "IA",
  investigating_group_value: "RCY",
  assignee_email_value: "",
  investigating_hub_id_value: "",
  entry_source_value: "GN",
  ticket_notes_value: "Incomplete address",
};

function downloadBase64Csv(base64, filename) {
  const bytes = atob(base64);
  const buf = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
  const blob = new Blob([buf], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [file, setFile] = useState(null);
  const [keywordsFile, setKeywordsFile] = useState(null);
  const [fields, setFields] = useState(DEFAULT_FIELDS);
  const [showTicketFields, setShowTicketFields] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const updateField = (key) => (e) =>
    setFields((f) => ({ ...f, [key]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) {
      setError("Please choose a CSV file first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.append("file", file);
    if (keywordsFile) form.append("keywords_file", keywordsFile);
    Object.entries(fields).forEach(([k, v]) => form.append(k, v));

    try {
      const res = await fetch("/api/clean-addresses", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed");
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const previewCols = result
    ? ["address_cleaned", "postcode_cleaned", "flags", "is_flagged"]
    : [];

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold text-slate-900">
          TNG Address Cleaning &amp; Flagging
        </h1>
        <p className="mt-2 text-slate-600">
          Upload a CSV with address and postcode columns. Addresses are cleaned and
          checked against a locality-keyword list; likely-bad ones are flagged and can
          be exported as a ticket-ready CSV.
        </p>

        <form
          onSubmit={handleSubmit}
          className="mt-6 space-y-5 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
        >
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Input CSV <span className="text-red-500">*</span>
            </label>
            <input
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">
              Locality keywords file (optional — .json array or .csv)
            </label>
            <input
              type="file"
              accept=".json,.csv"
              onChange={(e) => setKeywordsFile(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700"
            />
            <p className="mt-1 text-xs text-slate-400">
              If omitted, a built-in default list of common Malaysian locality words is used.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-500">Address column</label>
              <input
                value={fields.address_column}
                onChange={updateField("address_column")}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500">Postcode column</label>
              <input
                value={fields.postcode_column}
                onChange={updateField("postcode_column")}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500">Tracking ID column</label>
              <input
                value={fields.tracking_column}
                onChange={updateField("tracking_column")}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowTicketFields((v) => !v)}
              className="text-sm font-medium text-slate-600 underline underline-offset-2"
            >
              {showTicketFields ? "Hide" : "Show"} ticket export fields
            </button>
            {showTicketFields && (
              <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3">
                {[
                  ["type_value", "Type"],
                  ["sub_type_value", "Sub type"],
                  ["investigating_group_value", "Investigating group"],
                  ["assignee_email_value", "Assignee email"],
                  ["investigating_hub_id_value", "Investigating hub ID"],
                  ["entry_source_value", "Entry source"],
                  ["ticket_notes_value", "Ticket notes"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <label className="block text-xs font-medium text-slate-500">{label}</label>
                    <input
                      value={fields[key]}
                      onChange={updateField(key)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? "Processing…" : "Process"}
          </button>
        </form>

        {result && (
          <div className="mt-6 space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-700">
                <span className="font-semibold">{result.flagged_rows}</span> flagged of{" "}
                <span className="font-semibold">{result.total_rows}</span> rows
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() =>
                    downloadBase64Csv(result.result_csv_base64, "cleaned_addresses.csv")
                  }
                  className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
                >
                  Download result CSV
                </button>
                {result.ticket_csv_base64 && (
                  <button
                    onClick={() =>
                      downloadBase64Csv(result.ticket_csv_base64, "ticket_export.csv")
                    }
                    className="rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700"
                  >
                    Download ticket CSV
                  </button>
                )}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500">
                    {previewCols.map((c) => (
                      <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.preview.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      {previewCols.map((c) => (
                        <td key={c} className="whitespace-nowrap px-2 py-1.5 text-slate-700">
                          {String(row[c] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-slate-400">
                Showing first {result.preview.length} of {result.total_rows} rows.
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
