# Publishing on Google Play

A checklist for putting Painting TV on Google Play, with the answers to give in
Play Console's forms. Play Console changes its menus often; when a name below
doesn't match, look for the closest one.

Everything the listing needs is in the repository:

| What | Where |
| --- | --- |
| App bundle | `./gradlew bundleRelease` → `app/build/outputs/bundle/release/app-release.aab` |
| Title, short and full description, release notes (EN, FR) | `fastlane/metadata/android/<language>/` |
| 512 px icon, 1024×500 feature graphic, 1280×720 TV banner | `fastlane/metadata/android/en-US/images/` (regenerate with `python -m tools.app_icons`) |
| Privacy policy | `PRIVACY.md`, at <https://github.com/Mateleo/painting-tv/blob/main/PRIVACY.md> once the repository is public |
| TV screenshots, 1920×1080 (EN, FR) | `fastlane/metadata/android/<language>/images/tvScreenshots/` (regenerate with `python -m tools.store_screenshots`) |

## 1. Create the developer account

1. Go to <https://play.google.com/console/signup>, choose **Personal**, pay the
   one-time $25 fee and verify your identity. Verification can take a few days.
2. Your developer name and contact email are shown publicly on the store.
3. New personal accounts must run a **closed test with at least 12 testers for
   14 days in a row** before they can publish to everyone (step 7).

## 2. Create the app

**Home → Create app**: name *Painting TV*, default language *English (United
States)*, **App**, **Free**, then accept the declarations. Add *French (France)*
under **Store presence → Store listings** later.

## 3. Signing: keep the same key as GitHub

Google Play re-signs every app with an *app signing key*. Use your existing key
for it, so the Play version and the GitHub APK can update each other:

1. Upload your first bundle (step 6). When Play asks about app signing, choose
   **Use a different key** / **Export and upload a key from a Java keystore**.
2. Follow its instructions: download its `pepk.jar` tool and run the command it
   shows on `~/.config/painting-tv/release.jks` with the alias `painting-tv`.
   The passwords are in `local.properties`.
3. Upload the encrypted file it produces.

This choice can't be undone later. If Play generated a new key instead, its
version would refuse to install over the GitHub APK and the reverse.
After that, keep uploading bundles signed with the same key (it also serves as
the *upload key*).

## 4. Store listing

**Grow → Store presence → Main store listing**, for English and then French:
copy `title.txt`, `short_description.txt` and `full_description.txt`, and upload
`icon.png` and `featureGraphic.png`. Category: **Art & Design**. Contact email:
yours. Website: the GitHub repository.

Then add **Android TV** under **Advanced settings → Form factors** and, in the
TV section of the listing, upload `tvBanner.png` and the four TV screenshots
from `images/tvScreenshots/` of the same language: a painting filling the
screen, the remote controls, Settings, and a portrait in whole-painting framing.

They are rendered from `tools/screenshots.html`, a copy of the app's screens
with its sizes, colours and text, using real paintings from the dataset export.
If the interface changes, update that page to match and rerun
`python -m tools.store_screenshots`. Real captures work too: with the TV
connected over ADB, run `adb exec-out screencap -p > screenshot.png`.

## 5. App content forms

**Policy → App content**. Answers that match the app:

- **Privacy policy:** the `PRIVACY.md` link above.
- **Ads:** No.
- **App access:** All functionality is available without special access.
- **Content rating:** start the questionnaire, category *Reference, News or
  Educational* (or the closest one for art), and answer honestly. Some
  paintings show nudity in an artistic context; say so where asked. No violence
  beyond what classical paintings show, no user interaction, no purchases.
- **Target audience:** 18 and over, or 13 and over at the youngest. Don't
  include children: the Families policy brings extra requirements, and the
  paintings include nudity.
- **News app:** No.
- **Data safety:** the app collects and shares **no data**. It has no
  analytics, accounts or identifiers; downloading public files isn't data
  collection. Answer *No* to collection, then confirm that data is encrypted in
  transit (HTTPS only) and that there's no account to delete.
- **Government app / financial features / health:** No.
- **Foreground service permissions:** the app declares the *data sync* type.
  Explain: "Downloads the 2.9 GB painting collection the user starts from
  Settings, with progress shown in a notification, so it continues when the user
  leaves the app." Play may ask for a short video link: record the TV (a phone
  video is fine) pressing **Download all** and the notification appearing, and
  upload it to YouTube as unlisted.

## 6. Upload the bundle

```sh
./gradlew bundleRelease --no-daemon
```

**Test and release → Testing → Closed testing → Create track**, then **Create
release**, upload `app-release.aab` (signing questions: step 3), paste
`changelogs/12.txt` as the release notes, and roll out. Every later upload needs
a higher `versionCode`, the same as for GitHub releases.

## 7. Closed test: 12 testers for 14 days

1. In the closed track, add testers by email (a Google Group or an email list)
   and copy the **opt-in link**.
2. Send the link to at least 12 people. They open it while signed in to Google
   and accept; a Google TV or Android TV is needed to actually install the app.
   Ask them to keep the opt-in for the whole 14 days.
3. After 14 days, **Dashboard → Apply for production** asks a few questions
   about the test: how testers were recruited, the feedback received and what
   changed. Short honest answers are fine.

## 8. Production

Once approved, create a production release with the same bundle. The first
review usually takes a few days. Android TV apps also go through a TV quality
review; Play Console shows the result under **Release overview** with what to
fix if anything fails.

## Updating later

1. Bump `versionCode` and `versionName` in `app/build.gradle.kts` and add
   `fastlane/metadata/android/<language>/changelogs/<versionCode>.txt`.
2. Build both outputs: `./gradlew assembleRelease bundleRelease`. The APK goes
   to GitHub, the bundle to Play.

## Copyright

The collection includes paintings still under copyright. A rights holder can
file a complaint with Google, which may remove the app; repeated complaints put
the developer account at risk. Answer any complaint quickly, and remove the work
from the dataset when it's justified.
