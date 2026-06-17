import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from '../src/pages/Dashboard';
import Chat from '../src/pages/Chat';
import Settings from '../src/pages/Settings';

describe('Dashboard', () => {
  it('renders loading state initially', () => {
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(screen.getByText(/仪表盘|Dashboard/)).toBeTruthy();
  });
});

describe('Chat', () => {
  it('renders input and send button', () => {
    render(<MemoryRouter><Chat /></MemoryRouter>);
    expect(screen.getByPlaceholderText('输入消息...')).toBeTruthy();
    expect(screen.getByText('发送')).toBeTruthy();
  });
});

describe('Settings', () => {
  it('renders theme and api key sections', () => {
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(screen.getByText('API Key')).toBeTruthy();
    expect(screen.getByText('主题')).toBeTruthy();
  });
});
