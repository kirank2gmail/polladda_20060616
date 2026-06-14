"""
utils/email_sender.py
Sends emails via Gmail SMTP.
Each email has:
  - A plain HTML body (simple, readable in any client)
  - A PNG attachment of the same table rendered with Pillow
    (light gray background, black text, Open Sans font, color-coded cells, thin grid lines)
"""

import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime, timezone

import streamlit as st

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
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
            "C:/Windows/Fonts/opensans.ttf",
            "/Library/Fonts/OpenSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


# Cell background colours (RGB) — light gray background scheme
CELL_WIN  = (220, 255, 220)   # light green
CELL_LOSS = (255, 220, 220)   # light red
CELL_MISS = (255, 245, 210)   # light amber
CELL_NONE = (255, 255, 255)   # white
HDR_BG    = (230, 235, 245)   # Light gray header background
HDR_FG    = (20,  20,  20)    # Near-black header text
TEXT_BLK  = (20,  20,  20)    # near-black text
TEXT_WIN  = (20,  120,  40)   # dark green
TEXT_LOSS = (180,  20,  20)   # dark red
TEXT_MISS = (160,  90,   0)   # dark amber
ROW_ALT   = (240, 242, 245)   # Light gray for alternating rows
GRID_CLR  = (210, 215, 225)   # Thin light gray grid line color


def _text_colour(cell_bg: tuple) -> tuple:
    """Return appropriate text colour for a given cell background."""
    if cell_bg == CELL_WIN:   return TEXT_WIN
    if cell_bg == CELL_LOSS:  return TEXT_LOSS
    if cell_bg == CELL_MISS:  return TEXT_MISS
    return TEXT_BLK


def _cell_bg(val) -> tuple:
    """Determine cell background from raw value."""
    if val is None or val == "":  return CELL_NONE
    if val == "miss" or val == "M": return CELL_MISS
    if isinstance(val, str) and val.startswith("−"): return CELL_LOSS
    try:
        f = float(val)
        if f > 0: return CELL_WIN
        if f < 0: return CELL_LOSS
    except Exception:
        pass
    return CELL_NONE


def _fmt_val(val) -> str:
    if val is None or val == "": return "—"
    if val == "miss" or val == "M": return "M"  # Formatted as capital M
    if isinstance(val, str) and val.startswith("−"):
        return f"-{val[1:]}"
    try:
        f = float(val)
        if f > 0:  return f"+{f:.2f}"
        if f < 0:  return f"{f:.2f}"
        return "0"
    except Exception:
        return str(val)


def _render_table_png(headers: list[str], rows: list[list],
                       row_cell_bgs: list[list],
                       title: str, subtitle: str) -> bytes:
    """Render a table as a PNG image with full grid lines."""
    from PIL import Image, ImageDraw

    PADDING    = 20
    ROW_H      = 32
    HDR_ROW_H  = 36
    TITLE_H    = 50
    SUBTITLE_H = 28
    FOOTER_H   = 28

    font_hdr   = _get_font(15, bold=True)   # Bold column titles
    font_body  = _get_font(15, bold=False)
    font_title = _get_font(19, bold=True)
    font_sub   = _get_font(14, bold=False)

    # Measure column widths
    dummy = Image.new("RGB", (1, 1))
    dc    = ImageDraw.Draw(dummy)

    col_widths = []
    for ci, h in enumerate(headers):
        w = dc.textlength(h, font=font_hdr) + 28
        for row in rows:
            if ci < len(row):
                cw = dc.textlength(str(row[ci]), font=font_body) + 28
                w  = max(w, cw)
        min_w = 40 if ci == 0 else 65
        col_widths.append(max(int(w), min_w))

    total_w = sum(col_widths) + PADDING * 2
    total_h = (TITLE_H + SUBTITLE_H + HDR_ROW_H +
               len(rows) * ROW_H + FOOTER_H + PADDING * 2)

    img  = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Title
    y = PADDING
    draw.text((PADDING, y), title, font=font_title, fill=(20, 40, 80))
    y += TITLE_H

    draw.text((PADDING, y), subtitle, font=font_sub, fill=(100, 100, 120))
    y += SUBTITLE_H

    table_top_y = y

    # Header row background
    draw.rectangle([PADDING, y, total_w - PADDING, y + HDR_ROW_H], fill=HDR_BG)
    
    # Draw header text
    x = PADDING
    for ci, h in enumerate(headers):
        if ci == 0:
            tw  = draw.textlength(h, font=font_hdr)
            tx  = x + max(4, (col_widths[ci] - int(tw)) // 2)
            draw.text((tx, y + 10), h, font=font_hdr, fill=HDR_FG)
        else:
            draw.text((x + 8, y + 10), h, font=font_hdr, fill=HDR_FG)
        x += col_widths[ci]
    y += HDR_ROW_H

    # Data rows
    for ri, (row, bgs) in enumerate(zip(rows, row_cell_bgs)):
        # Alternating striping: light gray vs white
        row_bg = ROW_ALT if ri % 2 == 1 else (255, 255, 255)
        draw.rectangle([PADDING, y, total_w - PADDING, y + ROW_H], fill=row_bg)

        x = PADDING
        for ci, (cell_val, cell_bg) in enumerate(zip(row, bgs)):
            if cell_bg != row_bg and cell_bg != CELL_NONE:
                draw.rectangle([x + 1, y + 1, x + col_widths[ci] - 1, y + ROW_H - 1], fill=cell_bg)
            
            fg = _text_colour(cell_bg) if (cell_bg != row_bg and cell_bg != CELL_NONE) else TEXT_BLK

            if ci == 0:
                tw  = draw.textlength(str(cell_val), font=font_body)
                tx  = x + max(4, (col_widths[ci] - int(tw)) // 2)
                draw.text((tx, y + 8), str(cell_val), font=font_body, fill=fg)
            else:
                draw.text((x + 8, y + 8), str(cell_val), font=font_body, fill=fg)
            x += col_widths[ci]
        y += ROW_H

    table_bottom_y = y

    # Draw Gridlines (Vertical and Horizontal lines)
    # Horizontal grid lines
    grid_y = table_top_y
    draw.line([PADDING, grid_y, total_w - PADDING, grid_y], fill=GRID_CLR, width=1) # top boundary
    grid_y += HDR_ROW_H
    for _ in range(len(rows)):
        draw.line([PADDING, grid_y, total_w - PADDING, grid_y], fill=GRID_CLR, width=1)
        grid_y += ROW_H

    # Vertical grid lines
    grid_x = PADDING
    draw.line([grid_x, table_top_y, grid_x, table_bottom_y], fill=GRID_CLR, width=1) # left boundary
    for w in col_widths:
        grid_x += w
        draw.line([grid_x, table_top_y, grid_x, table_bottom_y], fill=GRID_CLR, width=1)

    # Footer
    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    draw.text((PADDING, y + 6), f"SportsPoll  ·  {now}", font=_get_font(13), fill=(160, 160, 170))

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


# ── Poll results ──────────────────────────────────────────────────────────────

def _build_poll_png(match: dict, votes: list[dict],
                    win_amounts: dict, display_names: dict,
                    tournament_name: str) -> bytes:
    options   = [o.strip() for o in match["options"].split("|") if o.strip()]
    total     = len(votes)
    by_opt    = {opt: [] for opt in options}
    voted_ids = set()

    for v in votes:
        opt = v.get("vote", "")
        if opt in by_opt:
            by_opt[opt].append(display_names.get(v["user_id"], v["user_id"]))
        voted_ids.add(v["user_id"])

    no_vote = sorted(display_names[u] for u in display_names if u not in voted_ids)

    headers = ["Option", "Votes", "%", "Win Points", "Voters"]
    rows    = []
    bgs     = []

    for opt in options:
        voters = by_opt[opt]
        count  = len(voters)
        pct    = f"{round(count / total * 100)}%" if total else "0%"
        amt    = win_amounts.get(opt, "—")
        names  = ", ".join(voters) if voters else "—"

        amt_bg = CELL_WIN if amt.startswith("+") else CELL_LOSS
        rows.append([opt, str(count), pct, amt, names])
        bgs.append([CELL_NONE, CELL_NONE, CELL_NONE, amt_bg, CELL_NONE])

    if no_vote:
        rows.append(["Did not vote", "—", "—", "—", ", ".join(no_vote)])
        bgs.append([CELL_MISS, CELL_NONE, CELL_NONE, CELL_NONE, CELL_NONE])

    # Strips everything after the initial match key marker (e.g. "M1")
    match_short = match['title'].split(" — ")[0]
    title    = f"Voting Results — {match_short}"
    subtitle = (f"{tournament_name}  ·  "
                f"{match['match_date']} {match['start_time']} "
                f"{match['timezone'].split('/')[-1]}  ·  "
                f"{total} total votes")

    return _render_table_png(headers, rows, bgs, title, subtitle)


def send_poll_results(match: dict, votes: list[dict],
                      win_amounts: dict, display_names: dict,
                      tournament_name: str):
    options   = [o.strip() for o in match["options"].split("|") if o.strip()]
    total     = len(votes)
    by_opt    = {opt: [] for opt in options}
    voted_ids = set()
    for v in votes:
        opt = v.get("vote","")
        if opt in by_opt:
            by_opt[opt].append(display_names.get(v["user_id"], v["user_id"]))
        voted_ids.add(v["user_id"])
    no_vote = sorted(display_names[u] for u in display_names if u not in voted_ids)

    rows_html = ""
    for opt in options:
        voters = by_opt[opt]
        count  = len(voters)
        pct    = round(count / total * 100) if total else 0
        amt    = win_amounts.get(opt, "—")
        names  = ", ".join(voters) if voters else "—"
        colour = "#16a34a" if amt.startswith("+") else "#dc2626"
        rows_html += f"""<tr>
          <td>{opt}</td><td>{count}</td><td>{pct}%</td>
          <td style="color:{colour};font-weight:700">{amt}</td>
          <td style="color:#555">{names}</td>
        </tr>"""

    no_vote_row = ""
    if no_vote:
        no_vote_row = (f'<tr><td colspan="5" style="color:#d97706">'
                       f'<b>Did not vote:</b> {", ".join(no_vote)}</td></tr>')

    match_short = match['title'].split(" — ")[0]
    html = f"""<!DOCTYPE html><html><body style="font-family:'Open Sans',Arial,sans-serif;
background:#fff;padding:20px;color:#111">
<h2 style="color:#1a1f35">Voting Results — {match_short}</h2>
<p><b>Tournament:</b> {tournament_name}<br>
<b>Date:</b> {match['match_date']} {match['start_time']} {match['timezone'].split('/')[-1]}<br>
<b>Total votes:</b> {total}</p>
<table border="1" cellpadding="8" cellspacing="0"
       style="border-collapse:collapse;width:100%;font-size:14px;border-color:#d2d7e1">
<tr style="background:#e6ebf5;color:#111;font-weight:bold">
<th>Option</th><th>Votes</th><th>%</th><th>Win Points</th><th>Voters</th>
</tr>{rows_html}{no_vote_row}</table>
<p style="font-size:11px;color:#aaa;margin-top:16px">
See attached PNG for shareable version.</p>
</body></html>"""

    png = _build_poll_png(match, votes, win_amounts, display_names, tournament_name)
    _send(
        subject  = f"[{tournament_name}] {match_short} — Voting Results",
        html_body= html,
        png_bytes= png,
        filename = f"poll_{match['match_id']}.png",
    )


# ── Leaderboard ───────────────────────────────────────────────────────────────

def _build_lb_png(match: dict, result: str,
                  leaderboard_rows: list[dict],
                  last5_match_ids: list[str],
                  last5_titles: dict,
                  tournament_name: str) -> bytes:

    # Clean the historical headers to only extract short names like "M1"
    m_hdrs   = [last5_titles.get(mid, mid[-6:]).split(" — ")[0] for mid in last5_match_ids]
    headers  = ["#", "Player", "Points", "Win%", "Missed"] + m_hdrs
    rows     = []
    bgs      = []
    medals   = ["1", "2", "3"]

    for i, row in enumerate(leaderboard_rows):
        rank = medals[i] if i < 3 else str(i + 1)
        name = str(row.get("name", ""))
        pts  = float(row.get("total_points", 0))
        winp = float(row.get("win_pct", 0))
        miss = int(row.get("missed", 0))

        pts_str = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"
        pts_bg  = CELL_WIN if pts >= 0 else CELL_LOSS

        match_vals = []
        match_bgs  = []
        for mid in last5_match_ids:
            val = row.get(mid)
            bg  = _cell_bg(val)
            match_vals.append(_fmt_val(val))
            match_bgs.append(bg)

        miss_bg = CELL_MISS if miss > 0 else CELL_NONE
        rows.append([rank, name, pts_str, f"{winp:.0f}%", str(miss)] + match_vals)
        bgs.append([CELL_NONE, CELL_NONE, pts_bg, CELL_NONE, miss_bg] + match_bgs)

    match_short = match['title'].split(" — ")[0]
    title    = f"Leaderboard — {tournament_name}"
    subtitle = f"After {match_short}  ·  Result: {result} Won"
    return _render_table_png(headers, rows, bgs, title, subtitle)


def send_leaderboard(match: dict, result: str,
                     leaderboard_rows: list[dict],
                     last5_match_ids: list[str],
                     last5_titles: dict,
                     tournament_name: str):

    m_hdrs    = "".join(f"<th>{last5_titles.get(mid,mid[-6:]).split(' — ')[0]}</th>"
                        for mid in last5_match_ids)
    medals    = ["🥇","🥈","🥉"]
    rows_html = ""

    for i, row in enumerate(leaderboard_rows):
        rank  = medals[i] if i < 3 else str(i + 1)
        name  = row.get("name","")
        pts   = float(row.get("total_points",0))
        winp  = float(row.get("win_pct",0))
        miss  = int(row.get("missed",0))
        pts_c = "#16a34a" if pts >= 0 else "#dc2626"
        pts_s = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"

        mcells = ""
        for mid in last5_match_ids:
            val = row.get(mid)
            if val is None:   mcells += "<td>—</td>"
            elif val == "miss" or val == "M": mcells += '<td style="color:#d97706">M</td>'
            else:
                try:
                    f   = float(val)
                    c   = "#16a34a" if f > 0 else ("#dc2626" if f < 0 else "#555")
                    txt = f"+{f:.2f}" if f > 0 else (f"{f:.2f}" if f < 0 else "0")
                    mcells += f'<td style="color:{c}">{txt}</td>'
                except Exception:
                    mcells += f"<td>{val}</td>"

        rows_html += f"""<tr>
          <td style="text-align:center">{rank}</td>
          <td><b>{name}</b></td>
          <td style="color:{pts_c};font-weight:700">{pts_s}</td>
          <td>{winp:.0f}%</td><td>{miss}</td>{mcells}</tr>"""

    match_short = match['title'].split(" — ")[0]
    html = f"""<!DOCTYPE html><html><body style="font-family:'Open Sans',Arial,sans-serif;
background:#fff;padding:20px;color:#111">
<h2 style="color:#1a1f35">Leaderboard — {tournament_name}</h2>
<p><b>After:</b> {match_short}<br><b>Result:</b> {result} Won</p>
<table border="1" cellpadding="8" cellspacing="0"
       style="border-collapse:collapse;width:100%;font-size:14px;border-color:#d2d7e1">
<tr style="background:#e6ebf5;color:#111;font-weight:bold">
<th>#</th><th>Player</th><th>Points</th><th>Win%</th><th>Missed</th>{m_hdrs}
</tr>{rows_html}</table>
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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipient, msg.as_string())
