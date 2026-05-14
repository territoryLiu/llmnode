import type React from 'react';
import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../App';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const passthrough = ({children}: {children?: React.ReactNode}) => children ?? null;
  return {
    ...actual,
    ResponsiveContainer: passthrough,
    AreaChart: passthrough,
    PieChart: passthrough,
    Area: () => null,
    Pie: passthrough,
    Cell: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
  };
});

const emptySnapshot = {
  backend_type: 'vllm',
  backend_ready: true,
  backend_error: null,
  backend_container: null,
  agent_state: {status: 'ready'},
  require_agent_ready: true,
  queue_length: 0,
  models: [],
  logs: [],
  events: [],
  runtime: {
    gateway: {
      host: '127.0.0.1',
      port: 4000,
      backend_url: 'http://127.0.0.1:8000',
      backend_model: 'Qwen',
      agent_base_url: 'http://127.0.0.1:4010',
      agent_status_url: 'http://127.0.0.1:4010/admin/status',
      require_agent_ready: true,
      queue_limit: 8,
      execution_limit: 1,
      api_key_configured: true,
    },
    agent: {
      host: '127.0.0.1',
      port: 4010,
      state: 'ready',
      poll_interval: 3,
      auto_recover: true,
      recovery_threshold: 3,
    },
    schedule: {
      timezone: 'Asia/Shanghai',
      work_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
      start_time: '09:00',
      end_time: '18:00',
      auto_stop_enabled: true,
      auto_start_enabled: true,
      cooldown_minutes: 10,
    },
    vllm: {
      backend_type: 'vllm',
      container_name: 'llmnode-vllm',
      image_name: 'vllm/vllm-openai:latest',
      model_dir: 'models/Qwen',
      model_name: 'Qwen',
      host_port: 8000,
      gpu_memory_utilization: 0.75,
      tensor_parallel_size: 1,
      max_model_len: 32768,
      max_num_seqs: 8,
      shm_size: '8g',
      enable_auto_tool_choice: false,
      reasoning_parser: null,
      tool_call_parser: null,
    },
    model_routes: [],
  },
};

function jsonResponse(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: {'Content-Type': 'application/json'},
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        return jsonResponse(emptySnapshot);
      }
      if (url.includes('/admin/request-logs')) {
        return jsonResponse({logs: []});
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse({keys: []});
      }
      if (url.includes('/admin/models')) {
        return jsonResponse({models: []});
      }
      if (url.includes('/admin/schedule')) {
        return jsonResponse({schedule: emptySnapshot.runtime.schedule});
      }
      if (url.includes('/admin/stream')) {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(emptySnapshot)}\n\n`));
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: {'Content-Type': 'text/event-stream'},
          }),
        );
      }
      return jsonResponse({});
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('Layout locale switch', () => {
  it('renders Chinese by default and switches to English', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
      expect(screen.getAllByText('总览').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getByRole('button', {name: '切换到 English'}));

    expect(screen.getAllByText('Overview').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', {name: 'Switch to Chinese'})).toBeInTheDocument();
  });

  it('does not render legacy connection config panel', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    expect(screen.queryByText('连接配置')).not.toBeInTheDocument();
    expect(screen.queryByText('API 地址')).not.toBeInTheDocument();
    expect(screen.queryByText('API 密钥')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('http://127.0.0.1:5173')).not.toBeInTheDocument();
  });
});
