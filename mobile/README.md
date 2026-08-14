# DaliJob mobile

Flutter client for Android and iOS. It currently provides account registration,
password-reset requests, mobile sign-in, secure refresh-token storage, session
restoration, sign-out, and the initial Matches/Automation/Account shell.

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
iOS Keychain through `flutter_secure_storage`.

## Verify

```sh
flutter analyze
flutter test
```
