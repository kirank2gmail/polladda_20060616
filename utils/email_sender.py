"""
utils/email_sender.py
Sends formatted HTML table emails via Gmail SMTP.
No images or graphics — clean HTML table layout easy to forward/share.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime             import datetime
import streamlit as st


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg():
    cfg = st.secrets.get("email", {})
    return cfg.get("sender",""), cfg.get("app_password",""), cfg.get("recipient","")

def email_configured() -> bool:
    s, p, r = _cfg()
    return bool(s and p and r)


# ── Style constants ───────────────────────────────────────────────────────────

CSS = """
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:20px; }
.wrap { max-width:700px; margin:auto; background:#fff;
        border-radius:8px; overflow:hidden;
        box-shadow:0 2px 8px rgba(0,0,0,0.12); }
.hdr { background:#1a1f35; color:#fff; padding:24px 28px; }
.hdr h1 { margin:0; font-size:22px; }
.hdr p  { margin:4px 0 0; color:#aab; font-size:13px; }
.body   { padding:24px 28px; }
table   { width:100%; border-collapse:collapse; margin-top:12px; font-size:14px; }
th      { background:#1a1f35; color:#fff; padding:10px 12px;
          text-align:left; font-weight:600; }
td      { padding:9px 12px; border-bottom:1px solid #e8e8e8; }
tr:nth-child(even) td { background:#f9f9f9; }
.win    { color:#16a34a; font-weight:700; }
.loss   { color:#dc2626; font-weight:700; }
.miss   { color:#d97706; }
.neu    { color:#666; }
.footer { padding:16px 28px; background:#f0f0f0;
          font-size:12px; color:#888; }
.badge  { display:inline-block; padding:2px 8px; border-radius:12px;
          font-size:12px; font-weight:700; }
.b-win  { background:#dcfce7; color:#15803d; }
.b-loss { background:#fee2e2; color:#b91c1c; }
.b-miss { background:#fef3c7; color:#92400e; }
"""


def _html_wrap(title: str, subtitle: str, body: str) -> str:
    now = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    return f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>{CSS}</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>🏆 {title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="body">{body}</div>
  <div class="footer">SportsPoll automated email &nbsp;·&nbsp; {now}</div>
</div>
</body></html>"""


# ── Poll results email ────────────────────────────────────────────────────────

def send_poll_results(match: dict, votes: list[dict],
                      win_amounts: dict, display_names: dict,
                      tournament_name: str):
    """
    Table showing each option with:
      vote count | voter names | calculated win pts
    """
    options = [o.strip() for o in match["options"].split("|") if o.strip()]
    total   = len(votes)

    # Group voters per option
    by_opt = {opt: [] for opt in options}
    for v in votes:
        opt = v.get("vote","")
        if opt in by_opt:
            by_opt[opt].append(display_names.get(v["user_id"], v["user_id"]))

    voted_ids = {v["user_id"] for v in votes}
    all_ids   = set(display_names.keys())
    no_vote   = [display_names[u] for u in all_ids if u not in voted_ids]

    rows_html = ""
    for opt in options:
        voters    = by_opt[opt]
        count     = len(voters)
        pct       = round(count / total * 100) if total else 0
        bar       = "█" * (pct // 10) + "░" * (10 - pct // 10)
        names_str = ", ".join(voters) if voters else "—"
        win_amt   = win_amounts.get(opt, "—")
        cls       = "win" if win_amt.startswith("+") else "loss"
        rows_html += f"""
        <tr>
          <td><b>{opt}</b></td>
          <td style="font-family:monospace">{bar} {pct}%</td>
          <td>{count}</td>
          <td class="neu">{names_str}</td>
          <td class="{cls}"><b>{win_amt}</b></td>
        </tr>"""

    no_vote_html = ""
    if no_vote:
        no_vote_html = f"""
        <p style="margin-top:20px;font-size:13px;color:#888;">
        <b>Did not vote:</b> {', '.join(sorted(no_vote))}
        </p>"""

    body = f"""
    <p style="font-size:14px;color:#555;">
      <b>Match:</b> {match['title']}<br>
      <b>Date:</b> {match['match_date']}  {match['start_time']} {match['timezone'].split('/')[-1]}<br>
      <b>Location:</b> {match['location']}<br>
      <b>Total votes:</b> {total}
    </p>
    <table>
      <tr>
        <th>Option</th><th>Poll</th><th>Votes</th>
        <th>Voters</th><th>Win Points</th>
      </tr>
      {rows_html}
    </table>
    {no_vote_html}"""

    html = _html_wrap(
        f"Voting Results — {match['title']}",
        tournament_name,
        body
    )
    _send(
        subject   = f"[{tournament_name}] {match['title']} — Voting Results",
        html_body = html,
    )


# ── Leaderboard email ─────────────────────────────────────────────────────────

def send_leaderboard(match: dict, result: str,
                     leaderboard_rows: list[dict],
                     last5_match_ids: list[str],
                     last5_titles: dict,
                     tournament_name: str):
    """
    Full leaderboard table + last 5 match point columns.
    """
    # Column headers for last 5 matches
    m_headers = "".join(
        f"<th>{last5_titles.get(mid, mid[-6:])}</th>"
        for mid in last5_match_ids
    )

    rows_html = ""
    medals    = ["🥇","🥈","🥉"]
    for i, row in enumerate(leaderboard_rows):
        rank  = medals[i] if i < 3 else str(i + 1)
        name  = row.get("name","")
        pts   = float(row.get("total_points", 0))
        winp  = float(row.get("win_pct", 0))
        miss  = int(row.get("missed", 0))
        pts_cls = "win" if pts >= 0 else "loss"
        pts_str = f"{pts:+.2f}"

        match_cells = ""
        for mid in last5_match_ids:
            val = row.get(mid)
            if val is None:
                match_cells += '<td class="neu">—</td>'
            elif val == "miss":
                match_cells += '<td class="miss">⚠️</td>'
            else:
                try:
                    f   = float(val)
                    cls = "win" if f > 0 else ("loss" if f < 0 else "neu")
                    txt = f"{f:+.2f}" if f != 0 else "0"
                    match_cells += f'<td class="{cls}">{txt}</td>'
                except Exception:
                    match_cells += f'<td class="neu">{val}</td>'

        rows_html += f"""
        <tr>
          <td style="text-align:center">{rank}</td>
          <td><b>{name}</b></td>
          <td class="{pts_cls}"><b>{pts_str}</b></td>
          <td class="neu">{winp:.0f}%</td>
          <td class="miss">{miss}</td>
          {match_cells}
        </tr>"""

    body = f"""
    <p style="font-size:14px;color:#555;">
      <b>After:</b> {match['title']}<br>
      <b>Result:</b> {result} Won<br>
      <b>Tournament:</b> {tournament_name}
    </p>
    <table>
      <tr>
        <th>#</th><th>Player</th><th>Points</th>
        <th>Win%</th><th>Missed</th>{m_headers}
      </tr>
      {rows_html}
    </table>
    <p style="font-size:12px;color:#aaa;margin-top:12px;">
      Match columns show last {len(last5_match_ids)} completed matches (latest first).
      ✅ correct &nbsp; ❌ wrong/penalty &nbsp; ⚠️ missed
    </p>"""

    html = _html_wrap(
        f"Leaderboard — {tournament_name}",
        f"After {match['title']} · {result} Won",
        body
    )
    _send(
        subject   = f"[{tournament_name}] Leaderboard after {match['title']}",
        html_body = html,
    )


# ── Send ──────────────────────────────────────────────────────────────────────

def _send(subject: str, html_body: str):
    sender, app_password, recipient = _cfg()
    if not all([sender, app_password, recipient]):
        raise ValueError("Email not configured in secrets.toml — "
                         "add [email] sender/app_password/recipient")

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"SportsPoll <{sender}>"
    msg["To"]       = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, recipient, msg.as_string())
