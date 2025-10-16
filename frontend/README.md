# Borg Web UI - Frontend

React frontend for the Borg Web UI application.

## Development

### Prerequisites

- Node.js 18+
- npm or yarn

### Setup

1. Install dependencies:
```bash
npm install
```

2. Start development server:
```bash
npm run dev
```

The frontend will be available at http://localhost:7879

### Build

To build for production:
```bash
npm run build
```

The built files will be in the `build/` directory.

### Features

- **Authentication**: JWT-based login/logout
- **Dashboard**: System metrics and status overview
- **Responsive Design**: Mobile-friendly interface
- **TypeScript**: Full type safety
- **Tailwind CSS**: Modern styling
- **React Query**: Server state management
- **React Hook Form**: Form handling
- **Lucide React**: Icon library

### Project Structure

```
src/
├── components/     # Reusable UI components
├── pages/         # Page components
├── hooks/         # Custom React hooks
├── services/      # API services
├── types/         # TypeScript type definitions
└── utils/         # Utility functions
```

### API Integration

The frontend communicates with the FastAPI backend through the `/api` proxy configured in `vite.config.ts`.

### Environment Variables

Create a `.env` file in the frontend directory:

```env
VITE_API_URL=http://localhost:7879/api
``` 