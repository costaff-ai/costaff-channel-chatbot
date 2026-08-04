# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-04

First stable release of the shared channel library. No code changes since
`v0.1.0-beta-3`. Channels should now pin
`costaff-channel-chatbot @ git+https://…@v0.1.0`.

## [0.1.0-beta-3] - 2026-07-14

First tagged release of the shared channel library. Channels should pin this
tag (`costaff-channel-chatbot @ git+https://…@v0.1.0-beta-3`) instead of
`@main` so their builds are reproducible.

### Added

- `ChannelRuntime` / `ChannelAdapter` abstraction shared by Telegram,
  Discord, WebChat OSS and WebChat Enterprise.
- ADK client with session helpers (`create_new_session` accepts initial
  session state), identity sync, and message splitting.
- Markdown formatters with result-envelope parsing (per-channel renderers).
- Shared internal-push receiver (`make_internal_push_router`) and
  `ChannelAdapter.push_frame` default, so async task results ("notify you
  later") are a shared capability instead of an Enterprise-only feature.
