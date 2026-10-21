# Publishing on Google Play

A click-by-click guide for putting Painting TV on Google Play, from the app
creation form to production, with every answer and text to paste. Menu names are
given as Play Console shows them in French, with the English name in
parentheses. Play Console renames menus from time to time; when one doesn't
match, look for the closest name or use the console's search bar.

**Already done:** the developer account, and the app created with the package
name `com.mateleo.paintingtv`.

**The whole journey**

| Phase | What | Time |
| --- | --- | --- |
| A | Store listing, store settings, App content forms | 1–2 hours |
| B | Build the bundle, create the closed test, set up signing | 30 minutes |
| C | 12 testers opted in for 14 days in a row | 14 days |
| D | Apply for production, answer the questionnaire | 15 minutes, then a few days of review |
| E | Production release and TV review | A few days |

Files used along the way:

| What | Where |
| --- | --- |
| Title, descriptions, release notes (EN, FR) | `fastlane/metadata/android/<language>/` |
| 512 px icon, 1024×500 feature graphic, 1280×720 TV banner | `fastlane/metadata/android/en-US/images/` |
| TV screenshots, 1920×1080 (EN, FR) | `fastlane/metadata/android/<language>/images/tvScreenshots/` |
| Privacy policy | <https://github.com/Mateleo/painting-tv/blob/main/PRIVACY.md> |
| App bundle | `app/build/outputs/bundle/release/app-release.aab` (phase B) |

The dashboard (**Tableau de bord**) lists the remaining setup tasks under
**Configurer votre application**. Each section below matches one of them; tick
them off in any order.

---

## Phase A — Listing and forms

### A1. Store settings

**Développer → Présence sur le Play Store → Paramètres du Play Store** (*Store
settings*):

- **Catégorie de l'application:** Appli → **Art et design** (*Art & Design*).
- **Tags:** pick up to five that fit, such as Art, Museums, Photography or
  Wallpapers, if offered.
- **Coordonnées:** this is shown publicly on the store.
  - **Adresse e-mail:** required. Consider a dedicated address, such as a new
    Gmail account or an alias, instead of your personal one.
  - **Site Web:** `https://github.com/Mateleo/painting-tv`
  - **Téléphone:** leave empty.

### A2. Main store listing, in English

**Développer → Présence sur le Play Store → Fiche Play Store principale**
(*Main store listing*). Copy each file's content as is:

| Field | Paste from |
| --- | --- |
| **Nom de l'application** (30 max) | `fastlane/metadata/android/en-US/title.txt` |
| **Brève description** (80 max) | `en-US/short_description.txt` |
| **Description complète** (4000 max) | `en-US/full_description.txt` (the `<b>` tags make bold headings; Play accepts them) |
| **Icône de l'application** | `en-US/images/icon.png` |
| **Image de présentation** (*feature graphic*) | `en-US/images/featureGraphic.png` |
| **Captures d'écran pour téléphone** | Leave empty for a TV-only app if Play allows; otherwise upload the TV screenshots there too |
| **Vidéo** | Leave empty |

The TV banner and TV screenshots go in after A3, once Android TV is enabled.
Click **Enregistrer** (*Save*).

### A3. Turn on Android TV

**Configuration → Paramètres avancés → Facteurs de forme** (*Advanced settings →
Form factors*) → **Ajouter un facteur de forme** → **Android TV**. Accept the
Android TV program terms if asked. If Play asks whether Android TV uses its own
release tracks or shares the existing ones, share them: the app only runs on TV
anyway. Play then asks for the TV assets in the store listing:

- **Bannière Android TV:** `en-US/images/tvBanner.png`
- **Captures d'écran Android TV:** the four files in
  `en-US/images/tvScreenshots/`, in order 1 to 4.

Phone screenshots aren't required for an app that only runs on TV. If the
listing still refuses to save without them, upload the TV screenshots as phone
screenshots too.

### A4. French listing

Back in **Fiche Play Store principale**, click **Gérer les traductions →
Ajouter vos propres traductions** (*Manage translations → Add your own*) →
**Français (France) – fr-FR**. Paste the files from `fastlane/metadata/android/fr-FR/`,
and upload the four screenshots from `fr-FR/images/tvScreenshots/`. The icon,
feature graphic and banner are shared with English.

### A5. App content forms

**Règles et programmes → Contenu de l'application** (*Policy and programs → App
content*). Each item opens a short form:

**Règles de confidentialité** (*Privacy policy*)
: `https://github.com/Mateleo/painting-tv/blob/main/PRIVACY.md`

**Accès à l'application** (*App access*)
: **Toutes les fonctionnalités de mon application sont disponibles sans accès
  spécial** (no login). Reviewers can press **Download all** like anyone else.

**Annonces** (*Ads*)
: **Non, mon application ne contient pas d'annonces.**

**Classification du contenu** (*Content rating*)
: **Démarrer le questionnaire.** Email: yours. Category: **Toutes les autres
  catégories d'applications** / *All Other App Types* (or *Reference, News or
  Educational* if that's offered). Answers:
  - Violence, fear, language, drugs, gambling, crude humour: **Non**. A few
    classical paintings show battles or myths; nothing is realistic,
    interactive or graphic.
  - **Sexuality / nudity: Oui**, and choose the option for **non-sexual nudity**
    in an artistic or educational context: some paintings, like Botticelli's
    *Birth of Venus*, show nudes.
  - Users interacting or communicating with each other: **Non**.
  - Sharing the user's location: **Non**.
  - Digital purchases: **Non**.
  - Unrestricted web browsing: **Non**.

  Submit; Play shows the resulting ratings (expect around PEGI 12 / Teen) and
  applies them.

**Public cible et contenu** (*Target audience and content*)
: Age groups: **18 ans et plus** only. Don't tick younger groups: they bring the
  Families policy, and the collection contains nudity. "Could your app
  unintentionally appeal to children?": **Non**.

**Applis d'actualités** (*News apps*)
: **Non.**

**Sécurité des données** (*Data safety*)
: - "Votre application collecte-t-elle ou partage-t-elle des types de données
    utilisateur requis ?": **Non**. The app has no account, analytics or
    identifiers; downloading public images isn't collecting user data.
  - If asked, "Toutes les données sont-elles chiffrées pendant leur transfert
    ?": **Oui** (HTTPS only).
  - Account creation / deletion: **Mon application ne permet pas aux
    utilisateurs de créer un compte**.
  - Review the summary and click **Envoyer**.

**Identifiant publicitaire** (*Advertising ID*)
: **Non.** The app doesn't use it and its manifest doesn't declare the
  `AD_ID` permission.

**Applis gouvernementales, Fonctionnalités financières, Applis de santé**
: **Non** to each.

**Autorisations du service de premier plan** (*Foreground service permissions*)
: This one appears after the first bundle upload (phase B). Choose **Synchronisation
  des données** (*Data sync*) and the task closest to *network transfer
  started by the user: upload or download*. Description to paste:

  > EN: When the user chooses "Download all" in Settings, the app downloads its
  > 2.9 GB painting collection (about 2,160 images) from Hugging Face. A
  > foreground service with a progress notification keeps the download running
  > when the user goes back to the slideshow or leaves the app. It stops when the
  > download finishes or the user presses Cancel.

  > FR : Lorsque l'utilisateur choisit « Tout télécharger » dans les Réglages,
  > l'application télécharge sa collection de tableaux (2,9 Go, environ 2 160
  > images) depuis Hugging Face. Un service de premier plan avec une
  > notification de progression permet au téléchargement de continuer quand
  > l'utilisateur revient au diaporama ou quitte l'application. Il s'arrête à la
  > fin du téléchargement ou quand l'utilisateur appuie sur Annuler.

  Play asks for a **video link**: film the TV with your phone for 20–30
  seconds (open Settings, press **Download all**, show the progress, press
  Home and show the notification or come back to see it still running), upload
  it to YouTube as **Non répertoriée** (*Unlisted*) and paste the link.

---

## Phase B — Bundle, closed test and signing

### B1. Build the bundle

Gradle needs the JDK used for this project. From the repository:

```sh
export JAVA_HOME=$HOME/.local/share/painting-tv-build/jdk-17.0.20.1+1
./gradlew bundleRelease --no-daemon
```

The bundle is `app/build/outputs/bundle/release/app-release.aab`, signed with
your release key (version 1.0.0, versionCode 12).

### B2. Create the closed test track

**Tester et publier → Tests → Tests fermés** (*Closed testing*). Play creates a
track named *Alpha* (or **Créer un canal** to name one):

1. **Pays/Régions:** **Ajouter des pays/régions** → select all.
2. **Testeurs:** choose **Groupes Google** and enter a Google Group address
   (create one free at <https://groups.google.com>, for example
   `painting-tv-testers@googlegroups.com`, set to "anyone can join"). A group is
   easier than an email list: testers join it themselves. An email list
   (**Listes d'adresses e-mail**) works too.
3. **Adresse e-mail ou URL des commentaires:** your contact email.
4. **Enregistrer.** The page then shows the **opt-in link** (*Rejoindre sur le
   Web*). Keep it for phase C.

### B3. Create the release, and set up signing

Still in the closed track: **Créer une release** (*Create release*).

**Signature d'application** (*App signing*) appears first, once per app. This
choice can't be undone, so read it through:

1. Click **Choisir une clé de signature** (or **Modifier la clé de signature**)
   → **Utiliser une autre clé** / **Exporter et importer une clé depuis un
   keystore Java** (*Export and upload a key from Java keystore*). Do **not**
   keep "Clé générée par Google": a Google key would make the Play version and
   the GitHub APKs refuse to update each other.
2. Download the two files Play offers: the **PEPK tool** (`pepk.jar`) and the
   **encryption public key** (`encryption_public_key.pem`), into the same folder.
3. Play shows the exact command to run. It looks like this; use Play's version
   if it differs, with your keystore and alias:

   ```sh
   $HOME/.local/share/painting-tv-build/jdk-17.0.20.1+1/bin/java -jar pepk.jar \
     --keystore=$HOME/.config/painting-tv/release.jks --alias=painting-tv \
     --output=output.zip --include-cert --rsa-aes-encryption \
     --encryption-key-path=encryption_public_key.pem
   ```

   It asks for the keystore password, then the key password: both are the
   `release.storePassword` value in `local.properties`.
4. Upload `output.zip` with **Importer la clé de signature d'application**.
5. If Play offers to register a separate **clé d'importation** (*upload key*),
   skip it: your release key then also serves as the upload key. A separate
   upload key is safer but one more secret to keep; you can add one later.
6. **Enregistrer.** Under **Configuration → Intégrité de l'application →
   Signature d'application**, the **certificat de la clé de signature
   d'application** SHA-256 must read
   `9A:8D:F4:4E:50:98:7C:C6:B6:2E:56:F9:27:27:C4:EF:91:4A:36:92:62:D6:67:5C:87:E4:8F:91:F8:78:CF:F8`.

Then, in the release:

1. **App bundles → Importer:** `app-release.aab`.
2. **Nom de la release:** `1.0.0`.
3. **Notes de version:** paste between the language tags Play shows:

   ```
   <en-US>
   (content of fastlane/metadata/android/en-US/changelogs/12.txt)
   </en-US>
   <fr-FR>
   (content of fastlane/metadata/android/fr-FR/changelogs/12.txt)
   </fr-FR>
   ```

4. **Suivant** → read any warnings. A warning about missing deobfuscation
   files is expected and harmless (the app isn't minified).
5. **Enregistrer et publier** / **Envoyer pour examen**. The first review of a
   closed test takes from a few hours to a few days.

Complete the foreground service form (A5) now if it appeared.

---

## Phase C — 12 testers for 14 days

New personal accounts must have **at least 12 testers opted in to the closed
test for the last 14 days in a row** before applying for production. The clock
starts once the closed release is live and testers have joined.

1. Find 12 or more people with a Google account; a few spares help if someone
   leaves early. Owning a TV isn't required to opt in, but testers with a Google
   TV or Android TV can install the app and give real feedback, which helps in
   phase D.
2. Send them the group link and the opt-in link. Message to adapt:

   > **EN** — Hi! I'm publishing Painting TV, my offline painting slideshow
   > for Android TV, on Google Play. Google requires 12 testers for 14 days
   > before it goes public. Could you help?
   > 1. Join the group: https://groups.google.com/g/painting-tv-testers
   > 2. Accept the test with the same Google account: (opt-in link)
   > 3. If you have a Google TV or Android TV, install Painting TV from the
   >    Play Store on it and tell me what you think.
   > Please stay in the test for at least 14 days. Thank you!

   > **FR** — Salut ! Je publie Painting TV, mon diaporama de tableaux hors
   > ligne pour Android TV, sur Google Play. Google demande 12 testeurs pendant
   > 14 jours avant la publication. Tu peux m'aider ?
   > 1. Rejoins le groupe : https://groups.google.com/g/painting-tv-testers
   > 2. Accepte le test avec le même compte Google : (lien d'inscription)
   > 3. Si tu as une Google TV ou une Android TV, installe Painting TV depuis le
   >    Play Store et dis-moi ce que tu en penses.
   > Merci de rester inscrit au moins 14 jours !

3. Note the feedback you get and any fixes you make: phase D asks about them.
   Each fix is a new bundle with a higher `versionCode` uploaded to the same
   closed track.
4. The dashboard shows the count of opted-in testers and the days elapsed.

---

## Phase D — Apply for production

When the dashboard shows 12 testers for 14 days, **Tableau de bord → Demander
l'accès à la production** (*Apply for production*). Answer briefly and honestly,
for example:

- **How did you recruit testers?** Friends, family and colleagues, invited
  through a Google Group.
- **How easy was it to recruit?** Fairly easy / as it was.
- **Describe the engagement / feedback received:** what testers actually said
  (for example the download length, the screen saver setup, framing preferences).
- **What did you change based on it?** Your actual changes, or "no blocking
  issues were found; minor wording fixes".
- **Who is the app for?** People who want famous paintings on their TV,
  offline, without ads or accounts.
- **What makes it different?** 2,160 paintings at the best available
  resolution, fully offline after one download, a screen saver mode, no ads or
  tracking, open source.
- **Is the app ready for production?** Yes.

Google replies by email, usually within a week.

---

## Phase E — Production

1. **Tester et publier → Production → Pays/Régions:** add all.
2. **Créer une release** → **Ajouter depuis la bibliothèque** (*Add from
   library*) to reuse the tested bundle, or upload a newer one. Same release
   notes. **Envoyer pour examen.**
3. **Publishing overview** (**Vue d'ensemble de la publication**) shows the
   submitted changes. With **Publication gérée** (*Managed publishing*) off,
   the app goes live as soon as it's approved.
4. Android TV apps also go through a **TV quality review**. If it fails, Play
   Console lists the reasons under the release or in your inbox. Send them to
   Claude to fix; the manifest already declares the TV launcher, the banner and
   no touchscreen requirement.

---

## Updating the app later

1. Bump `versionCode` and `versionName` in `app/build.gradle.kts`, and add
   `fastlane/metadata/android/<language>/changelogs/<versionCode>.txt`.
2. Build both outputs with the same key:
   `./gradlew assembleRelease bundleRelease --no-daemon`. The APK goes to
   GitHub (see the README's Releases section), the bundle to Play.
3. **Production → Créer une release**, upload the bundle, paste the notes,
   **Envoyer pour examen**.

If the screens change, update `tools/screenshots.html` to match and rerun
`python -m tools.store_screenshots`. Real captures work too: with the TV
connected over ADB, `adb exec-out screencap -p > screenshot.png`.

## If something goes wrong

- **"Le nom du package est déjà utilisé"** or a package mismatch: the bundle's
  package is `com.mateleo.paintingtv`; the Play app must use exactly that.
- **"Vous avez importé un APK ou un Android App Bundle signé avec une clé
  différente"**: the bundle wasn't built with `~/.config/painting-tv/release.jks`.
  Check the `release.*` lines in `local.properties`.
- **"Le code de version 12 a déjà été utilisé"**: raise `versionCode`.
- **A copyright complaint:** Google forwards it by email. Answer quickly and
  remove the work from the dataset when the claim is justified; the README says
  rights holders can ask for removal.
- **A policy rejection:** the email names the policy. Fix it, resubmit, and use
  the appeal link only when you believe the reviewer is mistaken.
