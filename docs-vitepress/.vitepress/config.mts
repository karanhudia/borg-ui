import { defineConfig } from 'vitepress';

export default defineConfig({
 title: 'Borg Web UI',
 description: 'A modern web interface for Borg Backup management',
 cleanUrls: true,
 lastUpdated: true,
 appearance: 'dark',
 ignoreDeadLinks: true,
 head: [
 ['link', { rel: 'icon', href: '/favicon.png' }],
 ],
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
 { text: 'SSH Keys', link: '/ssh-keys' },
 { text: 'Cache (Redis)', link: '/cache' },
 { text: 'Reverse Proxy', link: '/reverse-proxy' },
 ],
 },
 {
 text: 'Operations',
 items: [
 { text: 'Security', link: '/security' },
 { text: 'Analytics', link: '/analytics' },
 { text: 'Beta Features', link: '/beta-features' },
 { text: 'Docker Hooks', link: '/docker-hooks' },
 ],
 },
 {
 text: 'Reference',
 items: [
 { text: 'Specification', link: '/specification' },
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
 copyright: 'Copyright © 2024 Karan Hudia',
 },
 outline: {
 level: [2, 3],
 label: 'On this page',
 },
 },
});
