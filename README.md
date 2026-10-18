# Painting TV

A quiet, offline painting slideshow for Android TV and Google TV: 2,160 famous
paintings, no account, ads, analytics, or server. Built with Kotlin and Compose
for TV; Python tools prepare the collection.

## Install on your TV

You need the TV and a computer. It takes about 10 minutes plus the collection
download.

**1. Download the APK.** On your computer, open the
[latest release](https://github.com/Mateleo/painting-tv/releases) and download
`painting-tv.apk`. The repository is private, so the TV can't fetch it directly.

**2. Allow installing apps on the TV.**

1. **Settings → System → About**, then press OK on **Android TV OS build** seven
   times until it says you are a developer.
2. **Settings → Apps → Security & restrictions → Unknown sources** and allow the
   app you will install from (your file manager, or Send Files to TV).

Menu names vary slightly between TV brands.

**3. Copy the APK to the TV and install it.** Pick one:

- **USB stick:** copy `painting-tv.apk` onto it, plug it into the TV, open it in
  a file manager app (e.g. *File Commander* or *X-plore* from the Play Store),
  and choose **Install**.
- **Over Wi-Fi:** install *Send Files to TV* on both your phone and the TV, send
  the APK, then open it on the TV and choose **Install**.
- **ADB** (computer on the same network): turn on **Settings → System →
  Developer options → Network debugging**, then run:

  ```sh
  adb connect TV_IP:5555        # accept the prompt on the TV
  adb install -r painting-tv.apk
  ```

**4. Download the collection.** Open **Painting TV**. On first launch, Settings
opens on **Download full collection (about 2.9 GB)**. Press OK and allow
notifications if asked. The paintings download from a public
[Hugging Face dataset](https://huggingface.co/datasets/Mateleo/painting-tv-collection)
in the background; close Settings to keep watching meanwhile. If the download
stops, press the button again; finished images are kept. Once every image has
been checked, the gallery switches over and works fully offline. Keep about
3 GB free.

**Updating:** install a newer `painting-tv.apk` the same way. Settings and the
collection are kept.

### Offline alternative: import a ZIP

The release also carries the collection as `painting-pack.zip.001` and `.002`
(GitHub limits files to 2 GiB). Download both parts, `painting-pack.parts.json`,
and `join-pack.py` into one folder, then join and verify them:

```sh
python join-pack.py painting-pack.parts.json --output painting-pack.zip
```

Copy `painting-pack.zip` to a USB stick and choose **Settings → Import collection
ZIP** (needs about 6 GB free while importing). If the TV has no file picker,
push it with ADB instead:

```sh
adb shell am start -n com.mateleo.paintingtv/.MainActivity   # creates the inbox
adb shell am force-stop com.mateleo.paintingtv
adb push painting-pack.zip /sdcard/Android/data/com.mateleo.paintingtv/files/inbox/collection.zip
adb shell am start -n com.mateleo.paintingtv/.MainActivity   # imports it
```

## Using it

- **Left / Right:** previous / next painting.
- **OK or any direction:** show the controls (they hide after five seconds).
- **Play/Pause, Next, Previous, Menu** remote keys work too.
- **Back:** close settings, then hide controls, then exit.

Settings: time per painting (5 s to 1 h, default 10 s), gentle zoom, captions,
**fill screen** or **whole painting** framing, and an **All / HD+ / 4K+** filter
by source resolution. Playback shuffles through every painting before repeating
and keeps the TV awake.

## The collection

Paintings come from the Anki deck
[Tableaux de maîtres : les 2000 plus vus](https://ankiweb.net/shared/info/171273480).
Its thumbnails were replaced by larger matching reproductions from WikiArt,
Wikimedia Commons, and museum open-access sources wherever one passed image
comparison and review. Nothing is upscaled or AI-generated. It is still mixed
resolution: 280 paintings fill a 4K screen natively, 583 fit in 4K with margins.
[catalog/quality-upgrade-report.csv](catalog/quality-upgrade-report.csv) lists
every painting's size and source. Titles and dates are as given by the deck.

Rights remain with their holders. Many works are public domain; some are under
Creative Commons or still in copyright. This is a personal, non-commercial
viewer.

## Development

Requires JDK 17, Android SDK 35, and [uv](https://docs.astral.sh/uv/).

```sh
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon
uv run --locked --extra images pytest
uv run --locked --extra images ruff check tools tests
uv run --locked --extra images ty check
```

The APK lands in `app/build/outputs/apk/debug/`. It is debug-signed; keep the
same key to install updates over an existing install. See
[tools/README.md](tools/README.md) for building and publishing the collection.
