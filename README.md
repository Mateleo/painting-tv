# Painting TV

A quiet, offline painting slideshow for Android TV and Google TV: 2,160 famous
paintings, with no account, ads, analytics, or server of its own. Built with
Kotlin and Compose for TV; Python tools prepare the collection.

<p align="center">
  <img src="docs/images/painting-tv.webp" alt="Painting TV showing Cézanne’s Still Life with Apples and a Pot of Primroses on a television" width="800">
</p>

- **2,160 paintings** from the Anki deck *Tableaux de maîtres : les 2000 plus
  vus*, upgraded to the largest matching reproductions found.
- **Fill screen or whole painting** framing, slow zoom, captions with artist,
  date and collection, and an **All / HD+ / 4K+** resolution filter.
- **Works offline** once the collection is downloaded, and doubles as the TV's
  **screen saver**.
- English or French interface, following the TV's language.

## Install on your TV

You need the TV and a computer. It takes about 10 minutes plus the collection
download.

**1. Download the APK.** On your computer, open the
[latest release](https://github.com/Mateleo/painting-tv/releases) and download
`painting-tv-<version>.apk` (for example, `painting-tv-1.0.0.apk`).
`SHA256SUMS.txt` next to it lets you check the download
(`sha256sum -c SHA256SUMS.txt`).

**2. Allow installing apps on the TV.**

1. **Settings → System → About**, then press OK on **Android TV OS build** seven
   times until it says you are a developer.
2. **Settings → Apps → Security & restrictions → Unknown sources** and allow the
   app you will install from (your file manager, or Send Files to TV).

Menu names vary slightly between TV brands.

**3. Copy the APK to the TV and install it.** Pick one:

- **USB stick:** copy the downloaded APK onto it, plug it into the TV, open it in
  a file manager app (e.g. *File Commander* or *X-plore* from the Play Store),
  and choose **Install**.
- **Over Wi-Fi:** install *Send Files to TV* on both your phone and the TV, send
  the APK, then open it on the TV and choose **Install**.
- **ADB** (computer on the same network): turn on **Settings → System →
  Developer options → Network debugging**, then run:

  ```sh
  adb connect TV_IP:5555        # accept the prompt on the TV
  adb install -r painting-tv-1.0.0.apk  # use the version you downloaded
  ```

**4. Download the collection.** Open **Painting TV**. On first launch, Settings
opens on **Download all · 2.9 GB**. Press OK and allow notifications if asked.
The paintings download from a public
[Hugging Face dataset](https://huggingface.co/datasets/Mateleo/painting-collection)
in the background, several at a time; close Settings to keep watching
meanwhile. Downloaded paintings join the slideshow as they arrive. **Cancel**
pauses the download and keeps what is already downloaded; **Resume download**
continues it. Once every image is in, the gallery works fully offline. Keep
about 3 GB free.

**Updating:** install the APK from a newer release the same way. Settings and the
collection are kept. Coming from a 0.x preview? Those were signed with a
different key, so uninstall the old app first and download the collection again. When the published collection changes, Settings offers
**Download update**; only new or changed paintings are downloaded.

## Using it

- **Left / Right:** previous / next painting.
- **OK or any direction:** show the controls (they hide after five seconds).
- **Play/Pause, Next, Previous, Menu** remote keys work too.
- **Back:** close settings or hide the controls, then exit.

Settings: time per painting (10 s to 1 h, default 30 s), slow zoom, captions,
**fill screen** or **whole painting** framing, and an **All / HD+ / 4K+** filter
by source resolution. With whole painting framing, a painting qualifies when one
edge reaches the screen (2160 px tall or 3840 px wide for 4K+); filling the
screen needs both. Playback shuffles through every painting before repeating,
even across restarts, and keeps the TV awake.

### As a screen saver

Painting TV can also play when the TV is idle. Choose it in **Settings → System
→ Ambient mode** (or **Screen saver**, depending on the TV). It uses the app's
settings and continues the same shuffle; any key press wakes the TV.

Google TV hides third-party screen savers from its settings. Set it with ADB
instead (see step 3 above to connect):

```sh
adb shell settings put secure screensaver_components com.mateleo.paintingtv/.PaintingDream
```

## The collection

Paintings come from the Anki deck
[Tableaux de maîtres : les 2000 plus vus](https://ankiweb.net/shared/info/171273480).
Its thumbnails were replaced by larger matching reproductions from WikiArt,
Wikimedia Commons, and museum open-access sources wherever one passed image
comparison and review. Nothing is upscaled or AI-generated. It is still mixed
resolution: 280 paintings fill a 4K screen natively, 583 fit in 4K with margins.
[catalog/quality-upgrade-report.csv](catalog/quality-upgrade-report.csv) lists
every painting's size and source. The app checks each downloaded image against
the SHA-256 in the published catalog. Dates are as given by the deck; titles too,
except that titles the deck gives in English are shown in French
([catalog/titles-fr.json](catalog/titles-fr.json)). Captions name the holding
collection where one is known ([catalog/collections.json](catalog/collections.json)).

Rights remain with their holders. Many works are public domain; some are under
Creative Commons or still in copyright. This is a personal, non-commercial
viewer. Rights holders who want a work removed can open an issue or a discussion
on the dataset.

## Development

Requires JDK 17, Android SDK 35, and [uv](https://docs.astral.sh/uv/).

```sh
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon
uv run --locked --extra images pytest
uv run --locked --extra images ruff check tools tests
uv run --locked --extra images ty check
```

The debug APK lands in `app/build/outputs/apk/debug/`. See
[tools/README.md](tools/README.md) for building and publishing the collection.

Launcher assets follow the [Android TV icon guidelines](https://developer.android.com/design/ui/tv/guides/system/tv-app-icon-guidelines):
the logo is a P built from rounded screen pixels, in white over Van Gogh's *Wheat
Field with Cypresses* (1889, The Met, public domain) for the adaptive icon and the 16:9
banner; the same vector is the monochrome and notification icon.
`uv run --locked --extra images python -m tools.app_icons` regenerates them all from the
bundled painting. The banner's name is set in Inter Display
([SIL Open Font License](tools/fonts/OFL.txt)). PNG copies in `mipmap-*dpi/` let file
managers show an icon for the APK.

## Releases

Every release APK includes its version: `painting-tv-<version>.apk`.
After setting `versionCode` and `versionName` in `app/build.gradle.kts` and
writing `docs/release-v<version>.md`, build and check the app with the commands
above, build the signed APK, then stage the release (example: 1.0.0):

```sh
./gradlew assembleRelease --no-daemon
python -m tools.prepare_release --tag v1.0.0
```

This reads Android's build metadata, checks that the APK version matches the
tag, and writes `data/release-v1.0.0/painting-tv-1.0.0.apk` and `SHA256SUMS.txt`.
Commit and push the version and notes, tag that commit, then create the release
with those two files:

```sh
git tag -a v1.0.0 -m "Painting TV 1.0.0"
git push origin v1.0.0
gh release create v1.0.0 --verify-tag \
  --title "Painting TV 1.0.0" --notes-file docs/release-v1.0.0.md \
  data/release-v1.0.0/painting-tv-1.0.0.apk data/release-v1.0.0/SHA256SUMS.txt
```

Release builds are signed with a key kept outside the repository. Point
`local.properties` at it:

```properties
release.storeFile=/path/to/release.jks
release.storePassword=…
release.keyAlias=painting-tv
release.keyPassword=…
```

Without these lines `assembleRelease` produces an unsigned APK. Sign every
release with the same key, or installed apps can't update. Its certificate
SHA-256 is
`9a8df44e50987cc6b62e56f92727c4ef914a369262d6675c87e48f91f878cff8`.

## License

The code is under the [MIT License](LICENSE). The paintings, their
reproductions and the published dataset are not covered by it; see
[The collection](#the-collection).
