# Manage local avatars

This is the #43 extension beyond Phase 6's fixed pairs and original exclusion of
a custom avatar editor. It adds creation from an existing image and, with #49,
editing/deletion of user-created avatars. Cropping, cloning voices and persistent
conversations are out of scope.
Historical Phase 6 evidence retains its original pair labels.

From `C:/docs/git/tHead`, in PowerShell 7, use this single preparation-and-launch
command:

```powershell
pwsh -NoProfile -File ./scripts/conversation.ps1 -FixtureProvider -InitializeBudget
```

Prerequisites: Windows 11, PowerShell 7, Python 3.12, uv 0.11.7, Git, the pinned
RTX 3090/CUDA runtime, an H.264/AAC MediaSource browser, supported installed
Microsoft Zira Desktop and/or Hazel Desktop English voice assets, network access
for initial model/tool downloads and a local JPEG or PNG portrait. See the
[conversation guide](windows-conversation.md) for setup. This command prepares
the real local speech/video pipeline and opens http://127.0.0.1:8765 with
no-cost deterministic provider answers. It requires no API key. Omit
`-FixtureProvider` for normal provider operation with a backend API key.

Open **Settings**, then choose **Create avatar**. Enter **My avatar**, pick a local JPEG/PNG and an
available **Voice**, inspect the preview and choose **Save avatar**. Expect a
confirmation and one entry under that name. Saving does not select the new
avatar or stop existing playback. Select it between turns, ask “What is a black
hole?”, then ask “How do we detect one?” and confirm retained context. Check
that the chosen voice is audible and the portrait produces moving synchronised
video. Stop during speech, switch to JFK or Grace, ask again, then choose
**New conversation**: text clears while the avatar and monthly accounting remain.
Move/delete the original image, restart with the same command and select the
saved avatar again: portrait and speech must still work.

For invalid input, give a text file a `.png` extension and select it. Save should
say “Image is corrupt or oversized; choose a valid JPEG or PNG” and preserve the
name and voice. Replace the file and retry. Cancel or Escape closes the form
without saving. Save is disabled while in progress; repeated submissions cannot
create duplicate names.

## Edit and delete

Select a user-created avatar in Settings and choose **Edit avatar**. The saved
name, voice and portrait preview are filled in. Replace the image and/or voice,
optionally change the name, then save. An empty image picker retains the saved
portrait. Saving updates the same identity without another catalogue entry.
Cancel or Escape discards edits. Invalid images and failed saves retain the
previous saved record and leave the form available for correction.

Editing/deletion require the interval between turns, after playback ends or
Stop releases resources. Saving the selected avatar prepares its portrait and
voice together before accepting another question. A preparation failure reports
an error rather than substituting a voice.

**Delete avatar** opens a confirmation naming the selected avatar. Cancel keeps
it. Confirming removes its saved record and portrait bytes, and explicitly
switches to the permanent default **JFK**. Built-in JFK and Grace cannot be edited
or deleted through either UI or API. Transcript, context and budget are retained.
Source image files and bundled assets are never deleted. Portrait bytes are
owned by their individual database record, so deleting one avatar cannot remove
another avatar's image. The single derived model-input image remains a reusable
output cache, replaced on the next imported-avatar preparation.

Manual scenario using the preparation-and-launch command above: create/select
an avatar, change image/voice, save and speak. Verify actual image/voice playback,
restart, reselect and check persistence. Cancel an edit and deletion and check
no changes. Delete the selected user avatar and check the named fallback to JFK,
retained transcript and subsequent speech. Confirm JFK stays available and has
no delete action. Native Windows listening/viewing is required to verify audible
voice identity and perceived synchronisation.

## Limits and voices

Names are trimmed, required, at most 80 Unicode characters, and unique using
Unicode case-insensitive comparison, including JFK and Grace. Spaces are allowed.
Names are labels; identities are generated separately and do not use filenames.

Uploads are at most 5 MiB (5,242,880 bytes) and 4096 pixels on each axis, at most
16,777,216 decoded pixels. The backend checks JPEG/PNG signatures and actually
decodes the image. Extensions, MIME types, browser filenames and source paths do
not determine storage. Oversized, unsupported and corrupt images are rejected.

Only supported Zira/Hazel local English voices appear. Voice names include their
English region. Unavailable choices are disabled. The application checks pinned
Windows assets, SAPI voice identity and English culture before offering voices,
and validates the chosen voice again on save and preparation. It never installs
or silently substitutes a voice. Restore the exact supported Desktop voice assets
using the [voice guide](windows-pairs.md), then restart to refresh availability.
A saved avatar whose voice later disappears reports preparation failure; select
a healthy avatar to recover without losing conversation context.

## Local storage and recovery

The default store is `%LOCALAPPDATA%/tHead/avatars.sqlite3`. Override the directory
with `-UserData C:/path/to/data`, `--user-data` or `THEAD_USER_DATA`. Launcher
preparation never deletes this store. Automated tests each use their own temporary
user-data directory. The database contains each avatar's stable identity, trimmed
name, voice reference and imported portrait bytes in one SQLite transaction.
A failed/interrupted transaction preserves existing avatars and cannot leave a
selectable partial record. There are no temporary uploaded files to accumulate.
The model uses one replaceable derived image in the server output directory;
the database is authoritative. Portraits never leave the computer through this
feature. Conversation text remains in memory and is not saved in this database.

Back up the database with the application stopped. If it becomes corrupt or
unreadable, the UI names the affected path and offers recovery: stop the app,
preserve the damaged database, restore a backup or move it aside, and restart.
Do not delete the only copy of needed portraits. Built-in avatars remain usable;
invalid saved records are reported without blocking healthy records. A broken
portrait reports preparation failure on selection; restore its database backup
or select a healthy avatar. An unavailable voice is never silently replaced.

## Verification scope

Focused browser tests exercise the real UI/upload API/storage with isolated data
and deterministic provider responses, replacing only speech/GPU media transport.
They cover creation, decoded-image/name validation, duplicate submission and names,
cancellation, failed saves, restart, source removal, saved selection, context,
Stop/reset and recovery. These checks cannot establish physical speaker output,
voice quality or perceived lip sync. Real Windows/GPU digital media observations
are distinct from human listening/viewing confirmation.

Observed on 2026-11-08 on native Windows 11 / RTX 3090 / Chromium: imported a
JPEG as **My avatar** with Microsoft Hazel Desktop; four complete responses
established digital audio onset, moving video and playback end. The run included
a contextual follow-up, Stop during non-silent advancing playback, replacement
with Grace, New conversation and a restart after deleting the source image.
The saved portrait/voice survived restart. Both supported voices passed native
availability checks. No paid provider requests were made. This is automated
digital media evidence, not a human listening or perceived lip-sync assessment.
