# Painting TV 1.0.0

The first stable release, and the first public one. Painting TV is a quiet,
offline painting slideshow for Android TV and Google TV: 2,160 famous paintings,
with no account, ads or analytics.

- Download the collection once from Settings; the gallery then works offline.
  Collection updates download only new or changed paintings, each checked
  against its SHA-256.
- Fill screen or whole painting framing, slow zoom, captions with artist, date
  and collection, and an **All / HD+ / 4K+** resolution filter.
- A shuffle that goes through every painting before repeating, even across
  restarts.
- Works as the TV's screen saver (Google TV needs one ADB command; see the
  README).
- English or French interface, following the TV's language.

**Upgrading from a 0.x preview:** 1.0.0 is signed with a new release key, so it
can't install over the previews. Uninstall Painting TV first, then install this
APK and download the collection again from Settings. Future releases will update
in place.

`SHA256SUMS.txt` verifies the APK download. The signing certificate's SHA-256 is
`9a8df44e50987cc6b62e56f92727c4ef914a369262d6675c87e48f91f878cff8`.

Validated with the Android build, JVM unit tests, lint, and Python checks; no TV
device test was run for this release.
