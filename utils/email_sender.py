"""
utils/email_sender.py
Sends emails via Gmail SMTP.
PNG attachment matches the HTML body style:
  - White background, clean table, generous padding
  - No emoji in cells — text only (W/L/M/A)
  - Medals as text (1,2,3) or rank number
  - Colour-coded cells: green=win, red=loss, amber=miss, grey=abandoned
"""

import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from datetime             import datetime

import streamlit as st


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg():
    cfg = st.secrets.get("email", {})
    return cfg.get("sender",""), cfg.get("app_password",""), cfg.get("recipient","")

def email_configured() -> bool:
    s, p, r = _cfg()
    return bool(s and p and r)


# ── Fonts ─────────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = (
        ["/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "C:/Windows/Fonts/arialbd.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "C:/Windows/Fonts/arial.ttf"]
    )
    for p in candidates:
        try:
            from PIL import ImageFont
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    from PIL import ImageFont
    return ImageFont.load_default()


# ── Colours ───────────────────────────────────────────────────────────────────

WHITE      = (255, 255, 255)
BLACK      = ( 20,  20,  20)
GREY_TEXT  = (100, 100, 100)
GREY_BG    = (245, 246, 248)   # alternating row
HDR_BG     = ( 40,  50,  80)   # dark header
HDR_TEXT   = (255, 255, 255)
GRID       = (210, 213, 220)   # grid lines

WIN_BG     = (209, 240, 215)   # light green
WIN_FG     = ( 14, 110,  36)   # dark green
LOSS_BG    = (252, 215, 215)   # light red
LOSS_FG    = (160,  20,  20)   # dark red
MISS_BG    = (255, 243, 205)   # light amber
MISS_FG    = (140,  80,   0)   # dark amber
ABAND_BG   = (220, 220, 220)   # light grey
ABAND_FG   = (110, 110, 110)   # mid grey
TITLE_FG   = ( 30,  40,  80)
SUB_FG     = ( 80,  90, 110)


def _cell_style(val):
    """Return (bg, fg, text) for a cell value."""
    if val is None or val == "":
        return None, BLACK, "—"
    if val == "A":
        return ABAND_BG, ABAND_FG, "A"
    if val == "miss" or val == "M":
        return MISS_BG, MISS_FG, "M"
    if isinstance(val, str) and val.startswith("−"):
        return LOSS_BG, LOSS_FG, f"-{val[1:]}"
    try:
        f = float(val)
        if f > 0:
            return WIN_BG,  WIN_FG,  f"+{f:.2f}"
        if f < 0:
            return LOSS_BG, LOSS_FG, f"{f:.2f}"
        return None, BLACK, "0"
    except Exception:
        return None, BLACK, str(val)


# ── PNG table renderer ────────────────────────────────────────────────────────

def _render_table_png(title: str, subtitle: str,
                       headers: list[str],
                       rows: list[list],
                       row_styles: list[list],   # list of list of (bg,fg,text) per cell
                       ) -> bytes:
    """
    Render a clean, readable table as PNG.
    Sizing matches the HTML email body style.
    """
    from PIL import Image, ImageDraw

    # Layout constants — generous, like the HTML version
    PAD        = 28          # outer padding
    ROW_H      = 44          # data row height
    HDR_H      = 44          # header row height
    TITLE_H    = 48
    SUBTITLE_H = 32
    FOOTER_H   = 32
    CELL_PAD   = 14          # horizontal padding inside cell

    font_title = _font(18, bold=True)
    font_sub   = _font(14, bold=False)
    font_hdr   = _font(15, bold=True)
    font_body  = _font(14, bold=False)
    font_body_b= _font(14, bold=True)
    font_foot  = _font(12, bold=False)

    # Measure column widths
    dummy = Image.new("RGB", (1, 1))
    dc    = ImageDraw.Draw(dummy)

    col_widths = []
    for ci, h in enumerate(headers):
        w = int(dc.textlength(h, font=font_hdr)) + CELL_PAD * 2
        for row, styles in zip(rows, row_styles):
            if ci < len(row):
                txt = styles[ci][2] if styles else str(row[ci])
                cw  = int(dc.textlength(str(txt), font=font_body)) + CELL_PAD * 2
                w   = max(w, cw)
        # Minimum widths per column type
        if ci == 0:   w = max(w, 50)   # rank — narrow
        elif ci == 1: w = max(w, 130)  # player name — wider
        else:         w = max(w, 80)   # data columns
        col_widths.append(w)

    total_w = sum(col_widths) + PAD * 2
    total_h = (PAD + TITLE_H + SUBTITLE_H + HDR_H
               + len(rows) * ROW_H + FOOTER_H + PAD)

    img  = Image.new("RGB", (total_w, total_h), WHITE)
    draw = ImageDraw.Draw(img)

    # Title
    y = PAD
    draw.text((PAD, y), title, font=font_title, fill=TITLE_FG)
    y += TITLE_H

    draw.text((PAD, y), subtitle, font=font_sub, fill=SUB_FG)
    y += SUBTITLE_H

    # Header row
    draw.rectangle([PAD, y, total_w - PAD, y + HDR_H], fill=HDR_BG)
    x = PAD
    for ci, h in enumerate(headers):
        # Center rank, left-align rest
        if ci == 0:
            tw = int(dc.textlength(h, font=font_hdr))
            draw.text((x + (col_widths[ci] - tw) // 2, y + 14),
                      h, font=font_hdr, fill=HDR_TEXT)
        else:
            draw.text((x + CELL_PAD, y + 14), h, font=font_hdr, fill=HDR_TEXT)
        x += col_widths[ci]
    y += HDR_H

    # Draw top border of data area
    draw.line([PAD, y, total_w - PAD, y], fill=GRID, width=1)

    # Data rows
    for ri, (row, styles) in enumerate(zip(rows, row_styles)):
        row_bg = GREY_BG if ri % 2 == 1 else WHITE
        draw.rectangle([PAD, y, total_w - PAD, y + ROW_H - 1], fill=row_bg)

        x = PAD
        for ci, (cell_bg, cell_fg, cell_txt) in enumerate(styles):
            # Paint cell background if coloured
            if cell_bg is not None and cell_bg != row_bg:
                draw.rectangle([x + 2, y + 3,
                                x + col_widths[ci] - 3,
                                y + ROW_H - 4],
                               fill=cell_bg)

            # Bold for rank and player columns
            f = font_body_b if ci <= 1 else font_body

            # Center rank column, right-align numeric data, left-align player
            tw = int(dc.textlength(cell_txt, font=f))
            if ci == 0:
                tx = x + (col_widths[ci] - tw) // 2
            elif ci >= 2:
                tx = x + col_widths[ci] - tw - CELL_PAD
            else:
                tx = x + CELL_PAD

            ty = y + (ROW_H - 16) // 2
            draw.text((tx, ty), cell_txt, font=f, fill=cell_fg)
            x += col_widths[ci]

        # Bottom grid line
        draw.line([PAD, y + ROW_H - 1, total_w - PAD, y + ROW_H - 1],
                  fill=GRID, width=1)
        y += ROW_H

    # Footer
    now = datetime.utcnow().strftime("%d %b %Y  %H:%M  UTC")
    draw.text((PAD, y + 8), f"SportsPoll  ·  {now}",
              font=font_foot, fill=GREY_TEXT)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(144, 144))
    return buf.getvalue()


# ── Poll results ──────────────────────────────────────────────────────────────

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
    no_vote = sorted(display_names[u] for u in display_names
                     if u not in voted_ids)

    # Build PNG table
    headers = ["Option", "Votes", "%", "Win Pts", "Voters"]
    rows, styles = [], []
    for opt in options:
        voters = by_opt[opt]
        count  = len(voters)
        pct    = f"{round(count/total*100)}%" if total else "0%"
        amt    = win_amounts.get(opt, "—")
        names  = ", ".join(voters) if voters else "—"
        amt_bg = WIN_BG if str(amt).startswith("+") else LOSS_BG
        amt_fg = WIN_FG if str(amt).startswith("+") else LOSS_FG
        rows.append([opt, str(count), pct, amt, names])
        styles.append([
            (None, BLACK, opt),
            (None, BLACK, str(count)),
            (None, BLACK, pct),
            (amt_bg, amt_fg, str(amt)),
            (None, GREY_TEXT, names),
        ])
    if no_vote:
        nv = ", ".join(no_vote)
        rows.append(["Did not vote", "—", "—", "—", nv])
        styles.append([
            (MISS_BG, MISS_FG, "Did not vote"),
            (None, BLACK, "—"),
            (None, BLACK, "—"),
            (None, BLACK, "—"),
            (None, GREY_TEXT, nv),
        ])

    title    = f"Voting Results — {match['title']}"
    subtitle = (f"After: {match['match_date']} {match['start_time']} "
                f"{match['timezone'].split('/')[-1]}  ·  {total} votes  ·  {tournament_name}")
    png = _render_table_png(title, subtitle, headers, rows, styles)

    # HTML body
    rows_html = ""
    for opt in options:
        voters = by_opt[opt]
        count  = len(voters)
        pct    = round(count/total*100) if total else 0
        amt    = win_amounts.get(opt, "—")
        names  = ", ".join(voters) if voters else "—"
        colour = "#16a34a" if str(amt).startswith("+") else "#dc2626"
        rows_html += f"""<tr>
          <td>{opt}</td><td>{count}</td><td>{pct}%</td>
          <td style="color:{colour};font-weight:700">{amt}</td>
          <td style="color:#555">{names}</td>
        </tr>"""
    if no_vote:
        rows_html += (f'<tr><td colspan="5" style="color:#d97706">'
                      f'<b>Did not vote:</b> {", ".join(no_vote)}</td></tr>')

    html = f"""<!DOCTYPE html><html><body
      style="font-family:Arial,sans-serif;background:#fff;padding:24px;color:#111">
      <h2 style="color:#1a2850">Voting Results — {match['title']}</h2>
      <p><b>Tournament:</b> {tournament_name}<br>
         <b>Date:</b> {match['match_date']} {match['start_time']}
         {match['timezone'].split('/')[-1]}<br>
         <b>Total votes:</b> {total}</p>
      <table border="1" cellpadding="10" cellspacing="0"
             style="border-collapse:collapse;width:100%;font-size:14px">
        <tr style="background:#28324f;color:#fff">
          <th>Option</th><th>Votes</th><th>%</th>
          <th>Win Points</th><th>Voters</th>
        </tr>{rows_html}
      </table>
      <p style="font-size:11px;color:#aaa;margin-top:16px">
        See attached PNG for shareable version.</p>
    </body></html>"""

    _send(subject  = f"[{tournament_name}] {match['title']} — Voting Results",
          html_body= html, png_bytes=png,
          filename = f"poll_{match['match_id']}.png")


# ── Leaderboard ───────────────────────────────────────────────────────────────

def send_leaderboard(match: dict, result: str,
                     leaderboard_rows: list[dict],
                     last5_match_ids: list[str],
                     last5_titles: dict,
                     tournament_name: str):

    import re

    def _mlabel(mid):
        m = re.search(r'M0*(\d+)', mid, re.IGNORECASE)
        if m: return f"M{m.group(1)}"
        m = re.search(r'(\d+)$', mid)
        if m: return f"M{int(m.group(1))}"
        return mid[-4:]

    m_labels = [last5_titles.get(mid, _mlabel(mid)) for mid in last5_match_ids]
    medals   = ["1", "2", "3"]

    # ── Build PNG ─────────────────────────────────────────────────────────────
    headers = ["#", "Player", "Points", "Win%", "Missed"] + m_labels
    rows, styles = [], []

    for i, row in enumerate(leaderboard_rows):
        rank  = medals[i] if i < 3 else str(i + 1)
        name  = str(row.get("name", ""))
        pts   = float(row.get("total_points", 0))
        winp  = float(row.get("win_pct", 0))
        miss  = int(row.get("missed", 0))

        pts_str = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"
        pts_bg  = WIN_BG  if pts >= 0 else LOSS_BG
        pts_fg  = WIN_FG  if pts >= 0 else LOSS_FG
        miss_bg = MISS_BG if miss > 0 else None
        miss_fg = MISS_FG if miss > 0 else BLACK

        row_cells  = [rank, name, pts_str, f"{winp:.0f}%", str(miss)]
        row_styles = [
            (None,   BLACK,   rank),
            (None,   BLACK,   name),
            (pts_bg, pts_fg,  pts_str),
            (None,   GREY_TEXT, f"{winp:.0f}%"),
            (miss_bg,miss_fg, str(miss)),
        ]

        for mid in last5_match_ids:
            val = row.get(mid)
            bg, fg, txt = _cell_style(val)
            row_cells.append(txt)
            row_styles.append((bg, fg, txt))

        rows.append(row_cells)
        styles.append(row_styles)

    title    = f"Leaderboard — {tournament_name}"
    subtitle = f"After: {match['title']}  ·  Result: {result} Won"
    png = _render_table_png(title, subtitle, headers, rows, styles)

    # ── HTML body ─────────────────────────────────────────────────────────────
    m_hdrs    = "".join(f"<th>{lbl}</th>" for lbl in m_labels)
    medal_icons = ["🥇","🥈","🥉"]
    rows_html = ""

    for i, row in enumerate(leaderboard_rows):
        rank  = medal_icons[i] if i < 3 else str(i + 1)
        name  = row.get("name","")
        pts   = float(row.get("total_points",0))
        winp  = float(row.get("win_pct",0))
        miss  = int(row.get("missed",0))
        pts_c = "#16a34a" if pts >= 0 else "#dc2626"
        pts_s = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"

        mcells = ""
        for mid in last5_match_ids:
            val = row.get(mid)
            if val is None or val == "":
                mcells += "<td>—</td>"
            elif val == "A":
                mcells += '<td style="color:#888;background:#ddd">A</td>'
            elif val == "miss" or val == "M":
                mcells += '<td style="color:#d97706">M</td>'
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
          <td>{winp:.0f}%</td>
          <td>{miss}</td>{mcells}</tr>"""

    html = f"""<!DOCTYPE html><html><body
      style="font-family:Arial,sans-serif;background:#fff;padding:24px;color:#111">
      <h2 style="color:#1a2850">Leaderboard — {tournament_name}</h2>
      <p><b>After:</b> {match['title']}<br>
         <b>Result:</b> {result} Won</p>
      <table border="1" cellpadding="10" cellspacing="0"
             style="border-collapse:collapse;width:100%;font-size:14px">
        <tr style="background:#28324f;color:#fff">
          <th>#</th><th>Player</th><th>Points</th>
          <th>Win%</th><th>Missed</th>{m_hdrs}
        </tr>{rows_html}
      </table>
      <p style="font-size:12px;color:#aaa;margin-top:12px">
        Last {len(last5_match_ids)} completed matches (latest first).<br>
        See attached PNG for shareable version.</p>
    </body></html>"""

    _send(subject  = f"[{tournament_name}] Leaderboard after {match['title']}",
          html_body= html, png_bytes=png,
          filename = f"leaderboard_{match['match_id']}.png")


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
