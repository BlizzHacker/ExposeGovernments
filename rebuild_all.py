#!/usr/bin/env python3
"""
Normalize meeting names and rebuild ALL 508 pages with discrepancy filters.
"""
import json, re, html as htmlmod
from pathlib import Path
from datetime import datetime

MANIFEST = Path('/opt/meetings_manifest.json')
MEETINGS_DIR = Path('/var/www/exposemiamiok/html/meetings')

# Normalization map
NORMALIZE = {
    'City Council Regular Meeting': 'Miami City Council',
    'City Council Reg': 'Miami City Council',
    'Miami City Council Regular Meeting': 'Miami City Council',
    'Miami City Council Special Meeting': 'Miami City Council - Special Meeting',
    'City Council Special Meeting': 'Miami City Council - Special Meeting',
    'MIAMI CITY COUNCIL': 'Miami City Council',
    'Miami Special Utility Authority (MSUA) Regular Meeting': 'Miami Special Utility Authority (MSUA)',
    'Miami Special Utility Authority (MSUA) Special Meeting': 'Miami Special Utility Authority (MSUA) - Special Meeting',
    'Miami Special Utility Authority Regular Meeting': 'Miami Special Utility Authority (MSUA)',
    'Miami Special Utility Authority': 'Miami Special Utility Authority (MSUA)',
    'MSUA Regular Meeting': 'Miami Special Utility Authority (MSUA)',
    'Miami Special Utility Authority (MSUA) Reguar Meeting': 'Miami Special Utility Authority (MSUA)',
    'MIAMI SPECIAL UTILITY AUTHORITY (MSUA)': 'Miami Special Utility Authority (MSUA)',
    'Miami Industrial & Public Facilities Authority (MIPFA)': 'Miami Industrial & Public Facilities Authority (MIPFA)',
    'MIAMI INDUSTRIAL & PUBLIC FACILITIES AUTHORITY (MIPFA)': 'Miami Industrial & Public Facilities Authority (MIPFA)',
    'MIAMI MAIN STREET BOARD': 'Miami Main Street Board',
    'MIAMI LIBRARY BOARD': 'Miami Library Board',
    'MIAMI DOWNTOWN REDEVELOPMENT AUTHORITY (MDRA)': 'Miami Downtown Redevelopment Authority (MDRA)',
}

def normalize_name(name):
    """Normalize meeting name to standard form"""
    name = name.strip()
    if name in NORMALIZE:
        return NORMALIZE[name]
    # Try case-insensitive
    for key, val in NORMALIZE.items():
        if key.lower() == name.lower():
            return val
    return name

def detect_discrepancies(clip_id, meeting_dir, meeting):
    """Detect all types of discrepancies for a meeting"""
    issues = []
    
    # Check what files exist
    transcript_file = meeting_dir / 'transcript.json'
    audio_file = meeting_dir / 'audio.wav'
    agenda_file = meeting_dir / 'agenda.txt'
    minutes_file = meeting_dir / 'minutes.txt'
    
    has_transcript = transcript_file.exists() and transcript_file.stat().st_size > 100
    has_audio = audio_file.exists() and audio_file.stat().st_size > 1000
    has_agenda = agenda_file.exists() and agenda_file.stat().st_size > 100
    has_minutes = minutes_file.exists() and minutes_file.stat().st_size > 100
    
    # 1. Missing transcript (should be transcribed)
    if not has_transcript and has_audio:
        issues.append({
            'type': 'missing_transcript',
            'severity': 'warning',
            'title': 'Transcript Pending',
            'description': 'Audio available but AI transcription not yet complete. Queued for processing.'
        })
    
    if not has_transcript and not has_audio:
        issues.append({
            'type': 'missing_audio',
            'severity': 'warning', 
            'title': 'Audio Not Downloaded',
            'description': 'Meeting video exists on Granicus but audio has not been extracted yet.'
        })
    
    # 2. Missing official agenda
    if not has_agenda:
        issues.append({
            'type': 'missing_agenda',
            'severity': 'high',
            'title': 'No Official Agenda Document',
            'description': 'The city has not published an agenda document for this meeting on AgendaCenter. This is a transparency concern - agendas should be publicly available before meetings.'
        })
    
    # 3. Missing official minutes
    if not has_minutes:
        issues.append({
            'type': 'missing_minutes',
            'severity': 'high',
            'title': 'No Official Minutes Published',
            'description': 'The city has not published official minutes for this meeting. Under Oklahoma Open Meeting Act (25 O.S. § 308), minutes of all public meetings must be kept and made available.'
        })
    
    # 4. Check for city-published minutes
    city_has_minutes = meeting.get('has_city_minutes', False)
    city_has_agenda = meeting.get('has_city_agenda', False)
    
    if not city_has_minutes and has_transcript:
        issues.append({
            'type': 'city_no_minutes',
            'severity': 'medium',
            'title': 'City Has Not Published Minutes',
            'description': 'Our transcript is complete but the city has not published official minutes on AgendaCenter. This may indicate a delay or failure to comply with open records requirements.'
        })
    
    # 5. Content discrepancies (if both transcript and minutes exist)
    if has_transcript and has_minutes:
        try:
            with open(transcript_file) as f:
                transcript = json.load(f)
            
            minutes_text = open(minutes_file).read()
            
            segments = transcript.get('segments', [])
            
            # Check for executive session mentioned in transcript but not minutes
            exec_session_in_transcript = any(
                'executive session' in seg.get('text', '').lower() 
                for seg in segments[:20]
            )
            exec_session_in_minutes = 'executive session' in minutes_text.lower()
            
            if exec_session_in_transcript and not exec_session_in_minutes:
                # Find the segment
                for seg in segments[:20]:
                    if 'executive session' in seg.get('text', '').lower():
                        start = seg.get('start', 0)
                        minutes = int(start // 60)
                        seconds = int(start % 60)
                        issues.append({
                            'type': 'content_discrepancy',
                            'severity': 'critical',
                            'title': 'Executive Session Discussed But Not In Minutes',
                            'description': f'The transcript at [{minutes:02d}:{seconds:02d}] mentions an executive session, but the official minutes make no mention of it. Executive sessions must be recorded in minutes per Oklahoma law.',
                            'timestamp': f'{minutes:02d}:{seconds:02d}',
                            'transcript_text': seg.get('text', '')[:200]
                        })
                        break
            
            # Check for public testimony in transcript but "None" in minutes
            testimony_keywords = ['public input', 'public comment', 'citizen comment', 'personal appearance', 'concerned citizen']
            testimony_in_transcript = any(
                any(kw in seg.get('text', '').lower() for kw in testimony_keywords)
                for seg in segments[:15]
            )
            
            # Check if minutes say "None" for public input
            public_input_section = re.search(r'public\s+(?:input|comment|appearance).*?(?:none|no\s+one)', minutes_text.lower(), re.DOTALL)
            
            if testimony_in_transcript and public_input_section:
                for seg in segments[:15]:
                    if any(kw in seg.get('text', '').lower() for kw in testimony_keywords):
                        start = seg.get('start', 0)
                        minutes_s = int(start // 60)
                        seconds_s = int(start % 60)
                        issues.append({
                            'type': 'content_discrepancy',
                            'severity': 'critical',
                            'title': 'Public Testimony Occurred But Minutes Record "None"',
                            'description': f'The transcript at [{minutes_s:02d}:{seconds_s:02d}] shows public testimony took place, but the official minutes record "None" for public input. This is a potential violation of the Oklahoma Open Meeting Act.',
                            'timestamp': f'{minutes_s:02d}:{seconds_s:02d}',
                            'transcript_text': seg.get('text', '')[:200]
                        })
                        break
            
            # Check for votes in transcript not in minutes
            vote_keywords = ['motion', 'second', 'aye', 'nay', 'vote', 'approved', 'passed']
            votes_in_transcript = []
            for seg in segments:
                text = seg.get('text', '').lower()
                if any(kw in text for kw in ['motion', 'i move', 'seconded']):
                    start = seg.get('start', 0)
                    votes_in_transcript.append({
                        'time': start,
                        'text': seg.get('text', '')[:150]
                    })
            
            if len(votes_in_transcript) > 0 and len(minutes_text) < 500:
                issues.append({
                    'type': 'content_discrepancy',
                    'severity': 'medium',
                    'title': f'{len(votes_in_transcript)} Motions/Votes In Transcript',
                    'description': f'The transcript contains {len(votes_in_transcript)} motions or votes, but the official minutes are very brief ({len(minutes_text)} chars). Verify all actions were properly recorded.'
                })
            
        except Exception as e:
            pass
    
    return issues

def build_meeting_page(clip_id, meeting, issues):
    """Build HTML page for a meeting"""
    meeting_dir = MEETINGS_DIR / str(clip_id)
    name = meeting.get('name', 'Unknown Meeting')
    date = meeting.get('date', 'Unknown Date')
    guid = meeting.get('guid', '')
    duration = meeting.get('duration', '')
    
    # Determine status
    has_transcript = (meeting_dir / 'transcript.json').exists()
    has_minutes = (meeting_dir / 'minutes.txt').exists()
    has_agenda = (meeting_dir / 'agenda.txt').exists()
    
    critical_issues = [i for i in issues if i.get('severity') == 'critical']
    high_issues = [i for i in issues if i.get('severity') == 'high']
    medium_issues = [i for i in issues if i.get('severity') == 'medium']
    warning_issues = [i for i in issues if i.get('severity') == 'warning']
    
    total_issues = len(issues)
    
    if critical_issues:
        status_badge = '🔴 CRITICAL ISSUES'
        status_class = 'status-critical'
    elif high_issues:
        status_badge = '⚠️ DISCREPANCIES'
        status_class = 'status-warning'
    elif has_transcript and has_minutes:
        status_badge = '✅ Complete'
        status_class = 'status-complete'
    elif has_transcript:
        status_badge = '📝 Transcribed'
        status_class = 'status-transcribed'
    else:
        status_badge = '⏳ Pending'
        status_class = 'status-pending'
    
    # Build discrepancy section
    disc_html = ''
    if issues:
        disc_html = f'<section class="discrepancies"><h2>⚠️ Discrepancies & Missing Documents ({total_issues})</h2>\n'
        
        for issue in issues:
            sev = issue.get('severity', 'warning')
            icon = {'critical': '🔴', 'high': '⚠️', 'medium': '🟡', 'warning': '⏳'}.get(sev, 'ℹ️')
            
            disc_html += f'<div class="issue issue-{sev}">\n'
            disc_html += f'  <div class="issue-header">{icon} {htmlmod.escape(issue["title"])}</div>\n'
            disc_html += f'  <div class="issue-desc">{htmlmod.escape(issue["description"])}</div>\n'
            
            if issue.get('timestamp'):
                disc_html += f'  <div class="issue-timestamp">📍 <a href="#" onclick="seekTo(\'{issue["timestamp"]}\'); return false;">{issue["timestamp"]}</a></div>\n'
            
            if issue.get('transcript_text'):
                disc_html += f'  <div class="issue-quote">"{htmlmod.escape(issue["transcript_text"][:200])}"</div>\n'
            
            disc_html += '</div>\n'
        
        disc_html += '</section>\n'
    
    # Build document sections
    agenda_html = ''
    if has_agenda:
        try:
            agenda_text = open(meeting_dir / 'agenda.txt').read()
            preview = agenda_text.replace('\n', '<br>')
            agenda_html = f'''<section class="documents">
<h2>📄 Full Agenda</h2>
<div class="doc-preview">{preview}</div>
</section>'''
        except:
            pass
    
    minutes_html = ''
    if has_minutes:
        try:
            minutes_text = open(meeting_dir / 'minutes.txt').read()
            preview = minutes_text.replace('\n', '<br>')
            minutes_html = f'''<section class="documents">
<h2>📋 Full Minutes</h2>
<div class="doc-preview">{preview}</div>
</section>'''
        except:
            pass
    
    # Transcript section
    transcript_html = ''
    if has_transcript:
        try:
            transcript = json.load(open(meeting_dir / 'transcript.json'))
            segments = transcript.get('segments', [])
            
            transcript_html = '<section class="transcript"><h2>📝 AI Transcript</h2>\n'
            transcript_html += '<div class="transcript-segments">\n'
            
            for seg in segments:  # Show ALL segments
                start = seg.get('start', 0)
                minutes_s = int(start // 60)
                seconds_s = int(start % 60)
                text = htmlmod.escape(seg.get('text', ''))
                transcript_html += f'<div class="seg"><a href="#" onclick="seekTo({start}); return false;" class="ts">[{minutes_s:02d}:{seconds_s:02d}]</a> {text}</div>\n'
            
            transcript_html += '</div></section>\n'
        except:
            pass
    else:
        transcript_html = '<section class="transcript"><h2>⏳ Transcript Pending</h2><p>AI transcription is queued and will be processed automatically.</p></section>'
    
    # Video section
    video_html = ''
    if guid:
        video_url = f'https://miamiok.granicus.com/player/clip/{clip_id}'
        video_html = f'''<section class="video">
<h2>📹 Meeting Video</h2>
<iframe src="{video_url}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>
</section>'''
    

    # Audio section (for those who prefer listening)
    audio_html = ''
    audio_mp3 = meeting_dir / 'audio.mp3'
    if audio_mp3.exists() and audio_mp3.stat().st_size > 1000:
        mp3_size = round(audio_mp3.stat().st_size / 1024 / 1024, 1)
        audio_html = '<section class="audio">\n'
        audio_html += '<h2>\U0001f3a7 Audio Only</h2>\n'
        audio_html += '<p style="color:#666;font-size:0.9em;margin-bottom:10px">Prefer to listen? ' + str(mp3_size) + ' MB MP3 \u2014 right-click to download.</p>\n'
        audio_html += '<audio controls preload="none" style="width:100%">\n'
        audio_html += '<source src="audio.mp3" type="audio/mpeg">\n'
        audio_html += '</audio></section>\n'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{htmlmod.escape(name)} - {htmlmod.escape(date)} | ExposeMiamiOK</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
header {{ background: #1a1a2e; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
header h1 {{ font-size: 1.5em; margin-bottom: 5px; }}
header .meta {{ opacity: 0.8; font-size: 0.9em; }}
.back {{ display: inline-block; margin-bottom: 15px; color: #667; text-decoration: none; }}
.back:hover {{ color: #333; }}
.status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: bold; margin-top: 8px; }}
.status-critical {{ background: #ff4444; color: white; }}
.status-warning {{ background: #ff8800; color: white; }}
.status-complete {{ background: #44aa44; color: white; }}
.status-transcribed {{ background: #4488cc; color: white; }}
.status-pending {{ background: #888; color: white; }}
section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
section h2 {{ margin-bottom: 15px; color: #1a1a2e; }}
.discrepancies {{ border-left: 4px solid #ff8800; }}
.issue {{ padding: 12px; margin: 10px 0; border-radius: 6px; }}
.issue-critical {{ background: #fff0f0; border-left: 3px solid #ff4444; }}
.issue-high {{ background: #fff8f0; border-left: 3px solid #ff8800; }}
.issue-medium {{ background: #fffff0; border-left: 3px solid #ffcc00; }}
.issue-warning {{ background: #f0f8ff; border-left: 3px solid #4488cc; }}
.issue-header {{ font-weight: bold; margin-bottom: 5px; }}
.issue-desc {{ font-size: 0.9em; color: #555; }}
.issue-timestamp {{ margin-top: 5px; }}
.issue-timestamp a {{ color: #4488cc; text-decoration: none; font-family: monospace; }}
.issue-quote {{ margin-top: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 4px; font-style: italic; font-size: 0.85em; }}
.audio {{ border-left: 4px solid #a855f7; }}
.audio h2 {{ margin-bottom: 10px; }}
.doc-preview {{ background: #fafafa; padding: 15px; border-radius: 6px; font-family: monospace; font-size: 0.85em; white-space: pre-wrap; }}
.doc-note {{ margin-top: 10px; font-size: 0.85em; color: #666; }}
.transcript-segments {{ }}
.seg {{ padding: 6px 0; border-bottom: 1px solid #eee; }}
.seg .ts {{ color: #4488cc; text-decoration: none; font-family: monospace; font-size: 0.85em; margin-right: 8px; }}
.more {{ color: #666; font-style: italic; padding: 10px 0; }}
footer {{ text-align: center; padding: 20px; color: #666; font-size: 0.85em; }}
</style>
</head>
<body>
<div class="chapterbar" data-mw-chapterbar>
  <div class="chapterbar-in">
    <span class="cb-label">A chapter of the <a href="https://foundation.moveweight.com">Move Weight Foundation</a></span>
    <nav class="cb-links" aria-label="Foundation chapters">
      <a href="https://exposemiamiok.com" class="cur" aria-current="true">Miami, OK</a>
      <a href="https://exposesanangelo.com">San Angelo, TX</a>
      <a href="https://exposemississippi.com">Southaven, MS</a>
    </nav>
  </div>
</div>
<a href="/meetings/" class="back">← Back to All Meetings</a>
<header>
<h1>{htmlmod.escape(name)}</h1>
<div class="meta">📅 {htmlmod.escape(date)} | Clip #{clip_id}</div>
<div class="status-badge {status_class}">{status_badge}</div>
</header>

{disc_html}
{video_html}
{audio_html}
{transcript_html}
{agenda_html}
{minutes_html}

<footer>
<p>ExposeMiamiOK — Holding Power Accountable</p>
</footer>

<script>
function seekTo(seconds) {{
    var iframe = document.querySelector('iframe');
    if (iframe && iframe.contentWindow) {{
        // Try to seek the Granicus player
        try {{
            var url = new URL(iframe.src);
            url.searchParams.set('t', seconds);
            iframe.src = url.toString();
        }} catch(e) {{}}
    }}
}}
</script>
</body>
</html>'''
    
    return html

def main():
    print('=== REBUILDING ALL 508 PAGES WITH DISCREPANCY FILTERS ===\n')
    
    with open(MANIFEST) as f:
        manifest = json.load(f)
    
    # Normalize names
    for m in manifest:
        m['name'] = normalize_name(m.get('name', 'Unknown'))
    
    # Save normalized names
    with open(MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Build pages
    errors = 0
    critical_count = 0
    high_count = 0
    
    for m in manifest:
        clip_id = str(m.get('clip_id', ''))
        meeting_dir = MEETINGS_DIR / clip_id
        
        if not meeting_dir.exists():
            meeting_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Detect discrepancies
            issues = detect_discrepancies(clip_id, meeting_dir, m)
            
            # Count
            critical_count += len([i for i in issues if i.get('severity') == 'critical'])
            high_count += len([i for i in issues if i.get('severity') == 'high'])
            
            # Build page
            html = build_meeting_page(clip_id, m, issues)
            
            # Write
            with open(meeting_dir / 'index.html', 'w') as f:
                f.write(html)
        
        except Exception as e:
            print(f'ERROR clip {clip_id}: {e}')
            errors += 1
    
    print(f'\n=== RESULTS ===')
    print(f'Pages rebuilt: {len(manifest)}')
    print(f'Errors: {errors}')
    print(f'Critical issues found: {critical_count}')
    print(f'High severity issues found: {high_count}')

if __name__ == '__main__':
    main()
