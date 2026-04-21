# Tencent Meeting minutes — auto-router setup (macOS)

Context for anyone who wants to feed Tencent Meeting (腾讯会议) AI-generated transcripts into the weekly-review skill.

**What Tencent Meeting gives you:** after a meeting, the web app at `meeting.tencent.com` can export a "纪要文本" (AI-summarized transcript) as `.txt`. The filename follows a fixed convention:

```
<YYYYMMDDHHMMSS>-<room-name>-纪要文本-<N>.txt
```

Example: `20260413012330-sha7dow的快速会议-纪要文本-1.txt`. The timestamp is meeting start time in your local timezone. `<N>` is 1 by default; long meetings may produce `-2.txt`, `-3.txt`, etc.

**What the skill needs:** those files in a stable directory, pointed to by `config.tencent_meeting_dir`. This doc walks through making browser downloads land there automatically.

## Why this is non-trivial on macOS

The obvious approach — "configure the browser to download to `<target>/` for Tencent Meeting files" — does not exist. Browsers have one global download folder. Three obstacles show up in order:

1. **Tencent Meeting's local client does not store transcript data in readable form** — `~/Library/Containers/com.tencent.meeting/` has encrypted `.db` blobs and a proprietary KV store (`GLS_BINARY_LSB_FIRST`). Minutes live in Tencent's cloud; you have to export from the web UI.
2. **Filenames contain Chinese characters** — so any shell-level routing needs a UTF-8 locale at runtime.
3. **macOS Sonoma+ TCC blocks `launchd`-spawned processes from reading `~/Downloads`** by default — even when the agent is loaded in the user's GUI session.

The recipe below solves all three.

## Recipe

### 1. Router script

```bash
mkdir -p ~/bin ~/Work/Data/tencent-meeting-minutes
cat > ~/bin/route-tencent-minutes.sh <<'EOF'
#!/bin/bash
# Route Tencent Meeting minutes exports from ~/Downloads to the target directory.
# Triggered by launchd WatchPaths on ~/Downloads.
#
# Matches files that (a) contain "纪要" in name AND (b) start with a 14-digit timestamp
# (Tencent Meeting export convention: <YYYYMMDDHHMMSS>-<title>-<kind>-<n>.<ext>).
#
# UTF-8 locale must be set or bash glob won't match multibyte filenames when launchd
# invokes this script with an empty environment.
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

DST="$HOME/Work/Data/tencent-meeting-minutes"
SRC="$HOME/Downloads"
LOG="$HOME/Library/Logs/tencent-minutes-router.log"
mkdir -p "$DST"

shopt -s nullglob
for f in "$SRC"/*纪要*.txt "$SRC"/*纪要*.docx "$SRC"/*纪要*.pdf "$SRC"/*纪要*.md; do
  [ -f "$f" ] || continue
  base=$(basename "$f")
  [[ "${base:0:14}" =~ ^[0-9]{14}$ ]] || continue
  if [ -e "$DST/$base" ]; then
    new="${base%.*}.$(date +%s).${base##*.}"
    mv "$f" "$DST/$new" && echo "$(date '+%Y-%m-%d %H:%M:%S') moved (renamed): $base -> $new" >> "$LOG"
  else
    mv "$f" "$DST/" && echo "$(date '+%Y-%m-%d %H:%M:%S') moved: $base" >> "$LOG"
  fi
done
EOF
chmod +x ~/bin/route-tencent-minutes.sh
```

Change `DST` if you want a different target. Remember to match it with `config.tencent_meeting_dir` in the skill's `config.json`.

### 2. launchd LaunchAgent

```bash
LABEL="com.$USER.tencent-minutes-router"
cat > ~/Library/LaunchAgents/$LABEL.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$HOME/bin/route-tencent-minutes.sh</string>
    </array>
    <key>WatchPaths</key>
    <array>
        <string>$HOME/Downloads</string>
    </array>
    <key>ThrottleInterval</key>
    <integer>3</integer>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/tencent-minutes-router.err</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/$LABEL.plist
```

### 3. Grant Full Disk Access to `/bin/bash`

This is the TCC step and cannot be scripted — it needs a user click in System Settings:

1. System Settings → Privacy & Security → **Full Disk Access**
2. Click `+`, enter admin password if prompted
3. In the file picker, press **⌘⇧G** to open "Go to Folder"
4. Paste `/bin/bash` and hit Return
5. Add it and make sure the toggle is on

Without this step, the script silently sees an empty `~/Downloads` every time launchd fires it. The symptom is `launchctl print gui/$UID/$LABEL` showing `runs` increment while `files_in_src=0` if you log it.

**Security note:** this grants disk access to *any* bash script invoked. If that feels too broad, wrap the script in a minimal `.app` bundle and grant FDA only to the bundle. For a single-user machine, granting to `/bin/bash` is usually acceptable.

### 4. Verify

```bash
# Create a test file matching the expected pattern.
touch ~/Downloads/20260421000000-test-纪要文本-1.txt
sleep 5
ls ~/Work/Data/tencent-meeting-minutes/   # should contain it now
tail ~/Library/Logs/tencent-minutes-router.log
```

If it is still in `~/Downloads`, check `~/Library/Logs/tencent-minutes-router.err`. The most common cause is the Full Disk Access step being skipped — `launchctl print gui/$UID/$LABEL` will show `runs` incrementing while the file stays put. A one-time diagnostic is to add `echo "fired files=$(ls -1 "$SRC" | wc -l)" >> "$LOG"` at the top of the script; when launchd fires it, if `files=0` while `ls ~/Downloads` shows files, TCC is the cause.

## Uninstall

```bash
LABEL="com.$USER.tencent-minutes-router"
launchctl unload ~/Library/LaunchAgents/$LABEL.plist
rm ~/Library/LaunchAgents/$LABEL.plist ~/bin/route-tencent-minutes.sh
# (Optional) remove /bin/bash from Full Disk Access via System Settings.
```

The target directory (`~/Work/Data/tencent-meeting-minutes`) is left alone so the weekly-review collector keeps working over historical data.
