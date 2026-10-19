# Analytics and Privacy

Borg UI has optional product analytics.

It is used to understand broad product usage and error patterns. It should not include backup contents, Borg repository contents, passphrases, SSH keys, private hostnames, private IP addresses, or raw repository paths.

Analytics starts on. A banner after first login asks whether to keep it, and declining stops it from that point, though page views from before the answer are counted, and so are the answer itself and a later opt-out, each as a single event. Users can change the setting later in Settings > Preferences.

Events go to Borg UI's own analytics service at `t.borgui.com`, not to a third-party analytics product. The [trust page](trust) lists exactly what each event contains. Installs on versions before this change send to Umami Cloud until they are updated.

## Disable

Open Settings > Preferences and turn analytics off.

If analytics is disabled or preferences cannot be loaded, tracking is skipped.
