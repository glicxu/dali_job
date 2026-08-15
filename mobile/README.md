# DaliJob mobile

Flutter client for Android and iOS. It currently provides account registration,
password-reset requests, mobile sign-in, secure refresh-token storage, session
restoration, and sign-out. The authenticated experience includes PDF/TXT resume
upload, desktop-exported LinkedIn profile PDF import, manual resume entry, search criteria, weekly automatic matching,
tier usage, schedule controls, and the match inbox.

Signed-out users can also start one private guest match without creating an
account. The guest credential is stored separately in Android Keystore or iOS
Keychain and uses the backend's distinct `Guest` authorization scheme. The app
restores unfinished trials and offers two simple profile paths: upload a resume,
or enter one free-form background description when no resume is available. It
then provides deterministic readiness feedback, target role and location,
retry-safe matching, and the single best-result view. Guest work expires
automatically and can be deleted immediately from the app.

## Run locally

Start the API on port 5010, then run from this directory:

```sh
# Android emulator
flutter run --dart-define=DALIJOB_ENV=development \
  --dart-define=DALIJOB_API_BASE_URL=http://10.0.2.2:5010/api/v1/

# iOS simulator
flutter run --dart-define=DALIJOB_ENV=development \
  --dart-define=DALIJOB_API_BASE_URL=http://127.0.0.1:5010/api/v1/
```

The URL must end in `/`. Release builds reject non-HTTPS API URLs. Access
tokens stay in memory; rotating refresh tokens are held in Android Keystore or
iOS Keychain through `flutter_secure_storage`. Guest credentials use a separate
secure-storage key and are never sent as account bearer tokens.

## Verify

```sh
flutter analyze
flutter test
```
