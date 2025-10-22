# Borg Web UI Documentation

This directory contains the documentation site for Borg Web UI, hosted on GitHub Pages.

## Viewing the Documentation

Visit: **https://karanhudia.github.io/borg-ui**

## Setting Up GitHub Pages (First Time)

If you haven't enabled GitHub Pages for this repository yet, follow these steps:

1. **Go to Repository Settings**
   - Navigate to your repository on GitHub
   - Click on **Settings** (top menu)

2. **Enable GitHub Pages**
   - Scroll down to **Pages** section (left sidebar)
   - Under **Source**, select:
     - Branch: `main` (or `master`)
     - Folder: `/docs`
   - Click **Save**

3. **Wait for Deployment**
   - GitHub will build and deploy your site (takes 1-2 minutes)
   - You'll see a message: "Your site is published at https://karanhudia.github.io/borg-ui"

4. **Custom Domain (Optional)**
   - If you have a custom domain, add it in the same settings page
   - Create a CNAME file in this directory with your domain

## Local Development

To test the documentation site locally:

### Prerequisites
```bash
# Install Ruby and Bundler
brew install ruby  # macOS
# or use your system's package manager

# Install Jekyll
gem install bundler jekyll
```

### Run Locally
```bash
# Navigate to docs directory
cd docs

# Install dependencies
bundle install

# Serve the site
bundle exec jekyll serve

# Open browser
open http://localhost:4000/borg-ui
```

## Documentation Structure

```
docs/
├── _config.yml              # Jekyll configuration
├── index.md                 # Main documentation page
├── usage-guide.md           # Step-by-step guide for local and SSH backups
├── SPECIFICATION.md         # System architecture
├── DATABASE_PERSISTENCE.md  # Database guide
├── FUTURE_ENHANCEMENTS.md   # Roadmap
└── README.md               # This file
```

## Adding New Pages

1. Create a new `.md` file in the `docs/` directory
2. Add front matter at the top:
   ```yaml
   ---
   layout: default
   title: Your Page Title
   ---
   ```
3. Write your content in Markdown
4. Link to it from `index.md` or other pages
5. Commit and push - GitHub Pages will rebuild automatically

## Theme

We use the **Cayman** theme by GitHub. It's clean, modern, and mobile-responsive.

To change the theme, edit `_config.yml` and choose from:
- `jekyll-theme-cayman`
- `jekyll-theme-minimal`
- `jekyll-theme-architect`
- `jekyll-theme-slate`
- And more: https://pages.github.com/themes/

## Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [Markdown Guide](https://www.markdownguide.org/)
