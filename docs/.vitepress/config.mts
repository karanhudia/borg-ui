import { copyFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitepress';

const configDir = dirname(fileURLToPath(import.meta.url));
const docsRoot = resolve(configDir, '..');
const outDir = resolve(configDir, 'dist');
const publicManifests = ['announcements.json', 'plan-content.json'];

export default defineConfig({
  title: 'Borg Web UI',
  description: 'A modern web interface for Borg Backup management',
  cleanUrls: true,
  lastUpdated: true,
  appearance: 'dark',
  head: [['link', { rel: 'icon', href: '/favicon.png' }]],
  vite: {
    plugins: [
      {
        name: 'copy-docs-manifests',
        closeBundle() {
          for (const file of publicManifests) {
            copyFileSync(resolve(docsRoot, file), resolve(outDir, file));
          }
        },
      },
    ],
  },
  themeConfig: {
    logo: {
      light: '/logo-light.png',
      dark: '/logo-dark.png',
      alt: 'Borg Web UI',
    },
    siteTitle: false,
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Install', link: '/installation' },
      { text: 'Configure', link: '/configuration' },
      { text: 'GitHub', link: 'https://github.com/karanhudia/borg-ui' },
    ],
    sidebar: [
      {
        text: 'Getting Started',
        items: [
          { text: 'Installation', link: '/installation' },
          { text: 'Configuration', link: '/configuration' },
          { text: 'Usage Guide', link: '/usage-guide' },
          { text: 'Licensing', link: '/licensing' },
        ],
      },
      {
        text: 'Features',
        items: [
          { text: 'Notifications', link: '/notifications' },
          { text: 'Mounting Archives', link: '/mounting' },
          { text: 'Remote Machines', link: '/ssh-keys' },
          { text: 'Cache (Redis)', link: '/cache' },
          { text: 'Reverse Proxy', link: '/reverse-proxy' },
        ],
      },
      {
        text: 'Operations',
        items: [
          { text: 'Security', link: '/security' },
          { text: 'Disaster Recovery', link: '/disaster-recovery' },
          { text: 'Authentication and SSO', link: '/authentication' },
          { text: 'Analytics', link: '/analytics' },
          { text: 'Beta Features', link: '/beta-features' },
          { text: 'Docker Hooks', link: '/docker-hooks' },
          { text: 'Metrics', link: '/METRICS' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Architecture', link: '/SPECIFICATION' },
          { text: 'Job System', link: '/architecture/job-system' },
          { text: 'Development', link: '/development' },
          { text: 'Testing', link: '/testing' },
          { text: 'Contributing', link: '/contributing' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/karanhudia/borg-ui' },
    ],
    search: {
      provider: 'local',
    },
    editLink: {
      pattern: 'https://github.com/karanhudia/borg-ui/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },
    footer: {
      message: 'Distributed under the AGPL-3.0 License.',
      copyright: 'Copyright © 2024-present Karan Hudia',
    },
    outline: {
      level: [2, 3],
      label: 'On this page',
    },
  },
});
