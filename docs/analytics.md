# Analytics & Privacy

Borg UI collects **anonymous usage statistics** to help improve the product. We believe in **radical transparency**.

## Full Transparency

**[View our analytics dashboard publicly](https://analytics.nullcodeai.dev/)** - See exactly what we collect in real-time. No login required.

## What We Track

### We DO Collect

**Page Views:**
- Which pages you visit (Dashboard, Repositories, Archives, etc.)
- Navigation patterns and page transitions
- Session duration and visit frequency

**Feature Usage:**
- Button clicks (Backup Now, Create Repository, etc.)
- Feature interactions (mounting archives, scheduling backups)
- Settings changes (non-sensitive preferences)
- Search queries within the app

**Technical Information:**
- Browser type and version
- Operating system
- Screen resolution and device type
- Language preferences
- Error rates and crash reports

**Events We Track:**
- Repository actions (create, edit, delete, view info)
- Backup operations (start, complete, fail)
- Archive browsing (mount, unmount, file extraction)
- Schedule operations (create, edit, delete, enable/disable)
- SSH connection management (create, test, delete)
- Maintenance tasks (compact, check, prune)
- Authentication events (login, logout)

### We DO NOT Collect

- **Passwords** or authentication tokens
- **Encryption keys** or passphrases
- **Backup data** or file contents
- **File paths** or repository names
- **SSH keys** or connection credentials
- **IP addresses** - We do NOT collect or store IP addresses. All tracking is done without any IP address logging.
- **Hostnames** - We do NOT collect computer names or hostnames
- **User identifiers** - We do NOT track individual users across sessions
- **Repository URLs** or storage locations
- **Personal information** beyond voluntary submissions
- **Archive contents** or file names
- **Cookies** - We do NOT use cookies for tracking

## Why We Collect This

We use analytics data to:
- **Understand feature usage** - Which features are most valuable
- **Fix bugs faster** - Identify where users encounter errors
- **Prioritize development** - Focus on what users need most
- **Improve UX** - Discover pain points in user workflows
- **Platform compatibility** - Ensure compatibility across browsers/devices
- **Measure success** - Track adoption and retention

## How to Opt-Out

Analytics is **enabled by default** but you can disable it anytime:

1. Open Borg UI
2. Navigate to **Settings → Preferences**
3. Toggle off **"Enable anonymous usage analytics"**
4. Page will reload with tracking disabled

Your preference is stored in the database and respected across all sessions.

## Technical Implementation

**Analytics Platform:** [Matomo](https://matomo.org/) (open-source, self-hosted)
- **Instance:** `https://analytics.nullcodeai.dev`
- **No third-party services** (no Google Analytics, no Mixpanel)
- **Data stays under our control**
- **Open source** - You can inspect the code

**Privacy Protections:**
- **No IP tracking** - We do NOT log or store IP addresses
- **No cookies** - Tracking is completely cookieless
- **No user IDs** - We do NOT track individual users
- **No persistent identifiers** - Each session is anonymous
- **Respect Do Not Track** - Browser DNT setting is honored

**Tracking Method:**
- JavaScript tracking code loaded from our server
- Events sent via HTTP POST to our Matomo instance
- All data is completely anonymous and cannot be tied to individuals
- User preference checked before every tracking call

**Data Flow:**
1. User performs action (e.g., clicks "Backup Now")
2. Frontend checks if analytics is enabled (from database)
3. If enabled, sends anonymous event to Matomo (no IP, no user ID, no cookies)
4. If disabled, event is discarded client-side (never sent)

## Data Retention

- **Aggregate data:** Kept indefinitely for trend analysis (page view counts, feature usage stats)
- **No individual-level data:** We do not collect any data that can identify individuals, so there is no individual data to delete
- **User preferences:** Stored only in your local Borg UI database (not sent to analytics server)

## Privacy Rights

You have the right to:
- **Opt-out** at any time via Settings → Preferences
- **View collected data** on the public dashboard (all data is aggregated and anonymous)
- **Ask questions** about our practices
- **Provide feedback** on what we track - If you disagree with any data collection, please [open an issue](https://github.com/karanhudia/borg-ui/issues) and we will consider adjusting our tracking practices

**Important:** Since we do not collect any personally identifiable information (no IPs, no user IDs, no cookies), there is no individual-level data to delete. All data is anonymous aggregate statistics only.

## Centralized Analytics Model

**Important:** Borg UI uses a **centralized analytics model**:
- ALL Borg UI installations worldwide send data to ONE Matomo instance
- This allows us to understand global usage patterns
- Individual installations are not identifiable
- No tracking between instances (each install is anonymous)

This is different from self-hosted alternatives where each user runs their own analytics. We chose centralized analytics to better understand how the product is used globally while maintaining user privacy through anonymization.

## Open Source & Transparency

- All tracking code is open source (inspect `frontend/src/utils/matomo.ts`)
- Public analytics dashboard (no secrets, no hiding data)
- Privacy policy available in repository (`PRIVACY.md`)
- Opt-out mechanism built into the product

## Contact

Questions about analytics or privacy?
- **Open an issue:** [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- **Discussions:** [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
- **View live data:** [Analytics Dashboard](https://analytics.nullcodeai.dev/)

---

**Last Updated:** January 18, 2026

**Our Promise:** We collect only what helps us build a better product. No hidden tracking, no selling data, no dark patterns. Just transparent, user-focused analytics.
