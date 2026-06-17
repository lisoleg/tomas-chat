import { describe, it, expect } from 'vitest';
import type { SubsystemStatus, ChatMessage, TShieldStats } from '../src/types';

describe('Types', () => {
  it('SubsystemStatus has required fields', () => {
    const s: SubsystemStatus = {
      name: 'test', label: 'Test', status: 'online', health: 100,
      description: 'desc', accent: 'blue',
    };
    expect(s.status).toBe('online');
  });

  it('ChatMessage has role and content', () => {
    const msg: ChatMessage = {
      id: '1', role: 'user', content: 'hello', timestamp: new Date().toISOString(),
    };
    expect(msg.role).toBe('user');
  });

  it('TShieldStats has three sections', () => {
    const stats: TShieldStats = {
      dead_zone: { active: false, dead_count: 0, warning_count: 0, safe_count: 10, ratio: 0 },
      mus: { ambiguous_pairs: 0, total_boxes: 10, ratio: 0 },
      kappa_snap: { current_config: 'normal', event_count: 0, latency_ms: 1 },
    };
    expect(stats.dead_zone.safe_count).toBe(10);
    expect(stats.mus.total_boxes).toBe(10);
  });
});
