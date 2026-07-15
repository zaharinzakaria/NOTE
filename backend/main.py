"""Backend for the TNG bad-address cleaning & flagging tool.

Stateless: every request carries its own input file(s) and returns the result
in the response body (base64-encoded CSVs) — no database, no disk persistence
between requests, so it works the same whether there's 1 replica or many.
"""
import base64
import io
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Form, UploadFile, File, HTTPException

from address_cleaning import (
    DEFAULT_LOCALITY_KEYWORDS,
    clean_address,
    clean_postcode,
    get_flags,
    load_locality_keywords,
    sniff_delimiter,
)

app = FastAPI(title="TNG Address Cleaning")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _read_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8-sig")
    delimiter = sniff_delimiter(text[:2048])
    df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str)
    df.columns = df.columns.str.strip()
    return df


def _to_csv_base64(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")


@app.post("/api/clean-addresses")
async def clean_addresses(
    file: UploadFile = File(...),
    keywords_file: Optional[UploadFile] = File(None),
    address_column: str = Form("address"),
    postcode_column: str = Form("postcode"),
    tracking_column: str = Form("tracking_id"),
    type_value: str = Form("PE"),
    sub_type_value: str = Form("IA"),
    investigating_group_value: str = Form("RCY"),
    assignee_email_value: str = Form(""),
    investigating_hub_id_value: str = Form(""),
    entry_source_value: str = Form("GN"),
    ticket_notes_value: str = Form("Incomplete address"),
) -> dict:
    raw = await file.read()
    try:
        df = _read_csv(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    if address_column not in df.columns or postcode_column not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Expected columns '{address_column}' and '{postcode_column}', found: {list(df.columns)}",
        )

    if keywords_file is not None:
        kw_raw = await keywords_file.read()
        try:
            locality_keywords = load_locality_keywords(kw_raw, keywords_file.filename or "")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not parse keywords file: {exc}") from exc
    else:
        locality_keywords = set(DEFAULT_LOCALITY_KEYWORDS)

    df["postcode_cleaned"] = df[postcode_column].apply(clean_postcode)
    df["address_cleaned"] = df.apply(
        lambda row: clean_address(row[address_column], row["postcode_cleaned"]), axis=1
    )

    flag_results = df["address_cleaned"].apply(lambda addr: get_flags(addr, locality_keywords))
    df["flags"] = flag_results.apply(lambda f: ", ".join(f) if f else "")
    df["is_flagged"] = flag_results.apply(lambda f: bool(f))

    total = len(df)
    flagged = int(df["is_flagged"].sum())

    preview = df.head(50).where(pd.notna(df.head(50)), "").to_dict(orient="records")

    result_csv_b64 = _to_csv_base64(df)

    ticket_csv_b64 = None
    if tracking_column in df.columns:
        flagged_df = df[df["is_flagged"]].copy()
        if not flagged_df.empty:
            flagged_df["type"] = type_value
            flagged_df["sub_type"] = sub_type_value
            flagged_df["investigating_group"] = investigating_group_value
            flagged_df["assignee_email"] = assignee_email_value
            flagged_df["investigating_hub_id"] = investigating_hub_id_value
            flagged_df["entry_source"] = entry_source_value
            flagged_df["ticket_notes"] = ticket_notes_value
            ticket_cols = [
                tracking_column, "type", "sub_type", "investigating_group",
                "assignee_email", "investigating_hub_id", "entry_source", "ticket_notes",
            ]
            ticket_csv_b64 = _to_csv_base64(flagged_df[ticket_cols])

    return {
        "total_rows": total,
        "flagged_rows": flagged,
        "columns": list(df.columns),
        "preview": preview,
        "result_csv_base64": result_csv_b64,
        "ticket_csv_base64": ticket_csv_b64,
    }
