"""
utils/email_sender.py
Sends emails via Gmail SMTP.
Each email has:
  - A plain HTML body (simple, readable in any client)
  - A PNG attachment of the same table rendered with Pillow
    (light gray background, black text, Open Sans font, color-coded cells, thin grid lines)
"""

import re
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime, timezone

import streamlit as st


def _clean_match_title(title: str) -> str:
    """Extracts only prefix like 'M:14' or 'M 14' from match name."""
    m = re.match(r"^(M\s*[:\s-]?\s*\d+)", title, re.IGNORECASE)
    return m.group(1).strip() if m else title[:10].strip()


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg():
    cfg = st.secrets.get("email", {})
    return cfg.get("sender",""), cfg.get("app_password",""), cfg.get("recipient","")

def email_configured() -> bool:
    s, p, r = _cfg()
    return bool(s and p and r)


# ── Pillow image rendering ────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False):
    """
    Font priority updated to Open Sans across major environments:
      1. Open Sans (Standard system/user paths)
      2. Liberation Sans / DejaVu Sans (Ubuntu fallbacks)
      3. PIL default
    """
    from PIL import ImageFont

    candidates = []
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
            "C:/Windows/Fonts/opensansb.ttf",
            "/Library/Fonts/OpenSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
            "C:/Windows/Fonts/opensans.ttf",
            "/Library/Fonts/OpenSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            continue
    return ImageFont.load_default()


def _build_lb_png(match: dict, result: str, rows: list[dict],
                  last5_ids: list[str], last5_titles: dict, tournament_name: str) -> bytes:
    """
    Draws a presentation table into a byte stream array.
    Applies the shortened title change logic directly to image headers.
    """
    from PIL import Image, ImageDraw

    font_title  = _get_font(18, bold=True)
    font_header = _get_font(12, bold=True)
    font_data   = _get_font(12, bold=False)

    base_cols = ["Rank", "Player", "Points", "Win %", "🔥", "Missed"]
    all_cols  = base_cols + last5_ids

    col_widths = []
    for c in all_cols:
        if c == "Player":     col_widths.append(110)
        elif c in last5_ids:  col_widths.append(65)
        else:                 col_widths.append(55)

    row_h  = 26
    top_h  = 70
    width  = sum(col_widths) + 20
    height = top_h + (len(rows) * row_h) + 20

    img   = Image.new("RGB", (width, height), "#F4F4F2")
    draw  = ImageDraw.Draw(img)

    # Substring headers title string composition
    m_short = _clean_match_title(match["title\"])
    title_text = f"{tournament_name} — After {m_short} ({result})"
    draw.text((15, 15), title_text, fill="#1A1A24", font=font_title)

    # Headers setup
    curr_x = 10
    curr_y = top_h - row_h

    for idx, c in enumerate(all_cols):
        w = col_widths[idx]
        draw.rectangle([curr_x, curr_y, curr_x+w, curr_y+row_h], fill="#E5E4DE", outline="#D0CFC9")
        
        # Shorten titles displayed inside image headers
        if c in last5_titles:
            lbl = _clean_match_title(last5_titles[c])
        else:
            lbl = str(c)

        draw.text((curr_x+4, curr_y+6), lbl, fill="#1A1A24", font=font_header)
        curr_x += w

    # Core user value rendering grid loop
    curr_y = top_h
    for r in rows:
        curr_x = 10
        for idx, c in enumerate(all_cols):
            w = col_widths[idx]
            val = r.get(c, "")

            bg_color   = "#FFFFFF"
            text_color = "#1A1A24"

            if c in last5_ids:
                if val == "miss":
                    bg_color, text_color = "#FCE8E6", "#C5221F"
                    val = "⚠️"
                elif isinstance(val, (int, float)) or (isinstance(val, str) and val != ""):
                    sval = str(val)
                    if sval.startswith("+") or (not sval.startswith("−") and not sval.startswith("-") and float(val) > 0):
                        bg_color, text_color = "#E6F4EA", "#137333"
                        f_v = float(val)
                        val = f"+{f_v:.1f}"
                    else:
                        bg_color, text_color = "#FEF7E0", "#B06000"
                        f_v = abs(float(str(val).replace("−","-")))
                        val = f"-{f_v:.1f}"
                else:
                    val = "—"

            draw.rectangle([curr_x, curr_y, curr_x+w, curr_y+row_h], fill=bg_color, outline="#E2E1DA")

            display_str = str(val)
            if isinstance(val, float) and c == "Points":
                display_str = f"{val:.2f}"

            draw.text((curr_x+5, curr_y+6), display_str, fill=text_color, font=font_data)
            curr_x += w
        curr_y += row_h

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# ── Public APIs ───────────────────────────────────────────────────────────────

def send_poll_results(match: dict, result: str, total_pool: float,
                      winner_count: int, points_per_winner: float,
                      winner_names: list[str], tournament_name: str):
    """Simple notification body alerting users pool splits occurred."""
    s, p, r = _cfg()
    if not all([s, p, r]): return

    m_short = _clean_match_title(match["title\"])

    html = f"""<html><body>
    <h2>Results for {match['title']}</h2>
    <p><b>Winning Option:</b> {result}</p>
    <hr/>
    <p><b>Total Distribution Pool:</b> {total_pool:.2f} pts</p>
    <p><b>Number of Winners:</b> {winner_count}</p>
    <p><b>Points awarded per winner:</b> +{points_per_winner:.4f} pts</p>
    <br/>
    <h4>Winners List:</h4>
    <p>{", ".join(winner_names) if winner_names else 'None'}</p>
    </body></html>"""

    _send(
        subject=f"[{tournament_name}] Results: {m_short} ({result})",
        html_body=html
    )


def send_leaderboard(match: dict, result: str, leaderboard_rows: list[dict],
                     last5_match_ids: list[str], last5_titles: dict, tournament_name: str):
    """Assembles data rows into simple web-preview matrices plus Pillow attachment files."""
    s, p, r = _cfg()
    if not all([s, p, r]): return

    match_short = _clean_match_title(match["title\"])

    # Build basic fallback HTML table
    table_headers = ["Rank", "Player", "Points", "Win %", "🔥", "Missed"]
    for mid in last5_match_ids:
        t_str = last5_titles.get(mid, mid)
        table_headers.append(_clean_match_title(t_str))

    html_rows = []
    for r in leaderboard_rows:
        tds = []
        for h in table_headers:
            # Reverse column mapping search resolution back from shortened title
            lookup_key = h
            if h not in ["Rank", "Player", "Points", "Win %", "🔥", "Missed"]:
                for mid, t_str in last5_titles.items():
                    if _clean_match_title(t_str) == h:
                        lookup_key = mid
                        break

            val = r.get(lookup_key, "")
            if lookup_key in last5_match_ids:
                if val == "miss": val = "⚠️"
                elif val != "":
                    try:
                        f = float(str(val).replace("−","-"))
                        val = f"+{f:.1f}" if f > 0 else f"{f:.1f}"
                    except: pass
            tds.append(f"<td>{val}</td>")
        html_rows.append(f"<tr>{''.join(tds)}</tr>")

    html = f"""<html>
    <head><style>
      table {{ border-collapse: collapse; font-family: sans-serif; }}
      th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
      th {{ background-color: #eee; }}
    </style></head>
    <body>
    <h3>Leaderboard updated after {match['title']}</h3>
    <p>Result: <b>{result}</b></p>
    <table>
      <thead><tr>{"".join(f"<th>{h}</th>" for h in table_headers)}</tr></thead>
      <tbody>{"".join(html_rows)}</tbody>
    </table>
    <p style="font-size:12px;color:#aaa;margin-top:12px">
    Last {len(last5_match_ids)} completed matches (latest first).
    See attached PNG for shareable version.</p>
    </body></html>"""

    png = _build_lb_png(match, result, leaderboard_rows,
                        last5_match_ids, last5_titles, tournament_name)
    _send(
        subject  = f"[{tournament_name}] Leaderboard after {match_short}",
        html_body= html,
        png_bytes= png,
        filename = f"leaderboard_{match['match_id']}.png",
    )


# ── Send ──────────────────────────────────────────────────────────────────────

def _send(subject: str, html_body: str,
          png_bytes: bytes = None, filename: str = "table.png"):
    sender, app_password, recipient = _cfg()
    if not all([sender, app_password, recipient]):
        raise ValueError("Email not configured — add [email] to secrets.toml")

    msg            = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"SportsPoll <{sender}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html"))

    if png_bytes:
        part = MIMEBase("image", "png")
        part.set_payload(png_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        "attachment", filename=filename)
        msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, app_password)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
    except Exception as e:
        raise RuntimeError(f"SMTP execution failure: {e}")
