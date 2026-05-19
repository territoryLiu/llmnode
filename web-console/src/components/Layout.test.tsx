import type React from 'react';
import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../App';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  const passthrough = ({children}: {children?: React.ReactNode}) => children ?? null;
  const chartShell = () => null;
  return {
    ...actual,
    ResponsiveContainer: passthrough,
    AreaChart: chartShell,
    LineChart: chartShell,
    PieChart: chartShell,
    Area: () => null,
    Line: () => null,
    Pie: passthrough,
    Cell: () => null,
    CartesianGrid: () => null,
    Legend: () => null,
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
        api_key_configured: false,
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
    model_routes: [
      {
        name: 'qwen36-27b-fp8',
        display_name: 'Qwen 27B FP8',
        backend_model: 'Qwen/Qwen3.6-27B-FP8',
        backend_type: 'vllm',
        enabled: true,
      },
    ],
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

const emptyUsageOverview = {
  summary: {
    request_count: 0,
    success_count: 0,
    success_rate: 0,
    avg_latency_ms: 0,
    p95_latency_ms: 0,
    p99_latency_ms: 0,
    throughput_tokens_per_s: 0,
    tokens_observed_requests: 0,
    total_tokens: null,
    cache_creation_tokens: null,
    cache_read_tokens: null,
    cache_miss_tokens: null,
    cache_read_observed_requests: 0,
  },
  trend: [],
  breakdown: {
    models: [],
    backends: [],
    api_keys: [],
  },
  chart: {
    window: '12h',
    group_by: 'backend_type',
    totals: {
      prompt_tokens: 0,
      completion_tokens: 0,
      cache_creation_tokens: 0,
      cache_read_tokens: 0,
      cache_miss_tokens: 0,
      cache_tokens: 0,
      total_tokens: 0,
    },
    points: [],
    groups: [],
  },
};

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        return jsonResponse(emptySnapshot);
      }
      if (url.includes('/admin/request-logs')) {
        if (url.includes('/admin/request-logs/export')) {
          return Promise.resolve(
            new Response('id,request_id\n', {
              status: 200,
              headers: {'Content-Type': 'text/csv'},
            }),
          );
        }
        return jsonResponse({logs: [], total: 0, limit: 50, offset: 0});
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse({keys: []});
      }
      if (url.includes('/admin/overview/usage')) {
        return jsonResponse(emptyUsageOverview);
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
            controller.close();
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
    expect(screen.queryByDisplayValue('http://127.0.0.1:5173')).not.toBeInTheDocument();
  });

  it('does not render legacy api key input controls', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    expect(screen.queryByText('当前未配置 API 密钥。请先用控制命令创建一把 sk- 管理员密钥，然后在这里输入。')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: '保存密钥'})).not.toBeInTheDocument();
    expect(screen.queryByLabelText('输入 sk- 开头的 API 密钥')).not.toBeInTheDocument();
  });

  it('does not render legacy system status navigation entry', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    expect(screen.queryByRole('button', {name: '系统状态'})).not.toBeInTheDocument();
  });

  it('renders copy toast shell hidden by default', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    const toast = screen.getByTestId('copy-toast');
    expect(toast).toHaveClass('invisible');
    expect(toast).toHaveClass('opacity-0');
  });
});
