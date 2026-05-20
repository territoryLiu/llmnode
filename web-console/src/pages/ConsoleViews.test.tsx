import React from 'react';
import {render, screen, waitFor, within} from '@testing-library/react';
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
    LineChart: chartShell,
    Line: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
    AreaChart: chartShell,
    PieChart: chartShell,
    Area: () => null,
    Pie: passthrough,
    Cell: () => null,
    defs: passthrough,
    linearGradient: passthrough,
    stop: () => null,
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
        lifecycle_mode: 'managed_local',
        upstream_protocol: 'chat',
        upstream_base_url: 'http://127.0.0.1:8000/v1',
        upstream_model: 'Qwen/Qwen3.6-27B-FP8',
        upstream_auth_kind: 'none',
        upstream_auth_ref: null,
        source_kind: 'profile_seed',
        source_ref: 'vllm_qwen36-27b-FP8',
        stale: false,
        capabilities_json: {
          supports_responses: false,
          supports_chat: true,
          supports_messages: true,
          supports_stream: true,
          supports_function_tools: true,
          supports_builtin_tools: false,
          supports_previous_response_id_native: false,
          supports_json_schema: false,
        },
        native_protocols_json: ['chat', 'responses', 'messages'],
        adapter_policies_json: [],
        tool_policies_json: {
          openai_function_tools: true,
          anthropic_function_tools: true,
          builtin_tools: false,
        },
        protocol_features_json: {
          stream: true,
          count_tokens: true,
          json_schema: false,
          previous_response_id: true,
        },
      },
      {
        name: 'qwen36-35b-a3b-fp8',
        display_name: 'Qwen 35B A3B FP8',
        backend_model: 'Qwen/Qwen3.6-35B-A3B-FP8',
        backend_type: 'vllm',
        enabled: true,
        lifecycle_mode: 'managed_local',
        upstream_protocol: 'chat',
        upstream_base_url: 'http://127.0.0.1:8000/v1',
        upstream_model: 'Qwen/Qwen3.6-35B-A3B-FP8',
        upstream_auth_kind: 'none',
        upstream_auth_ref: null,
        source_kind: 'profile_seed',
        source_ref: 'vllm_qwen36-27b-FP8',
        stale: false,
        capabilities_json: {
          supports_responses: false,
          supports_chat: true,
          supports_messages: true,
          supports_stream: true,
          supports_function_tools: true,
          supports_builtin_tools: false,
          supports_previous_response_id_native: false,
          supports_json_schema: false,
        },
        native_protocols_json: ['chat', 'responses', 'messages'],
        adapter_policies_json: [],
        tool_policies_json: {
          openai_function_tools: true,
          anthropic_function_tools: true,
          builtin_tools: false,
        },
        protocol_features_json: {
          stream: true,
          count_tokens: true,
          json_schema: false,
          previous_response_id: true,
        },
      },
      {
        name: 'anthropic-claude',
        display_name: 'Anthropic Claude',
        backend_model: null,
        backend_type: null,
        enabled: true,
        lifecycle_mode: 'external',
        upstream_protocol: 'messages',
        upstream_base_url: 'https://api.anthropic.com',
        upstream_model: 'claude-sonnet',
        upstream_auth_kind: 'x_api_key',
        upstream_auth_ref: 'ANTHROPIC_KEY',
        source_kind: 'manual',
        source_ref: null,
        stale: false,
        capabilities_json: {
          supports_responses: false,
          supports_chat: false,
          supports_messages: true,
          supports_stream: true,
          supports_function_tools: true,
          supports_builtin_tools: false,
          supports_previous_response_id_native: false,
          supports_json_schema: false,
        },
        native_protocols_json: ['messages'],
        adapter_policies_json: [],
        tool_policies_json: {
          openai_function_tools: true,
          anthropic_function_tools: true,
          builtin_tools: false,
        },
        protocol_features_json: {
          stream: true,
          count_tokens: true,
          json_schema: false,
          previous_response_id: false,
        },
        recommended_runtime_semantics: {
          native_protocols_json: ['messages'],
          adapter_policies_json: [],
          protocol_features_json: {
            stream: true,
            count_tokens: true,
            json_schema: false,
            previous_response_id: false,
          },
        },
      },
      {
        name: 'legacy-qwen-route',
        display_name: 'Legacy Qwen Route',
        backend_model: 'Qwen/Qwen3.6-14B',
        backend_type: 'vllm',
        enabled: false,
        lifecycle_mode: 'managed_local',
        upstream_protocol: 'chat',
        upstream_base_url: 'http://127.0.0.1:18000/v1',
        upstream_model: 'Qwen/Qwen3.6-14B',
        upstream_auth_kind: 'none',
        upstream_auth_ref: null,
        source_kind: 'profile_seed',
        source_ref: 'vllm_qwen36-14b-legacy',
        stale: true,
        capabilities_json: {
          supports_responses: false,
          supports_chat: true,
          supports_messages: false,
          supports_stream: true,
          supports_function_tools: true,
          supports_builtin_tools: false,
          supports_previous_response_id_native: false,
          supports_json_schema: false,
        },
        native_protocols_json: ['chat'],
        adapter_policies_json: [],
        tool_policies_json: {
          openai_function_tools: true,
          anthropic_function_tools: true,
          builtin_tools: false,
        },
        protocol_features_json: {
          stream: true,
          count_tokens: false,
          json_schema: false,
          previous_response_id: false,
        },
        recommended_runtime_semantics: {
          native_protocols_json: ['chat'],
          adapter_policies_json: [],
          protocol_features_json: {
            stream: true,
            count_tokens: false,
            json_schema: false,
            previous_response_id: false,
          },
        },
      },
    ],
  },
};

const usageOverview = {
  summary: {
    request_count: 12345,
    success_count: 1,
    success_rate: 1,
    avg_latency_ms: 10,
    p95_latency_ms: 10,
    p99_latency_ms: 10,
    throughput_tokens_per_s: 50,
    tokens_observed_requests: 1,
    total_tokens: 12345678,
    cache_creation_tokens: 5,
    cache_read_tokens: 7,
    cache_miss_tokens: 0,
    cache_read_observed_requests: 1,
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
      prompt_tokens: 10,
      completion_tokens: 20,
      cache_creation_tokens: 5,
      cache_read_tokens: 7,
      cache_miss_tokens: 2,
      cache_tokens: 14,
      total_tokens: 42,
    },
    groups: [
      {
        group: 'vllm',
        label: 'vLLM',
        totals: {
          prompt_tokens: 12345,
          completion_tokens: 12345678,
          cache_creation_tokens: 5,
          cache_read_tokens: 7,
          cache_miss_tokens: 2,
          cache_tokens: 14,
          total_tokens: 3456789123,
        },
        points: [
          {
            bucket: '2026-05-15 08:00',
            label: '08:00',
            prompt_tokens: 10,
            completion_tokens: 20,
            cache_creation_tokens: 5,
            cache_read_tokens: 7,
            cache_miss_tokens: 2,
            cache_tokens: 14,
            total_tokens: 42,
            request_count: 1,
          },
        ],
      },
    ],
  },
};

const keyListResponse = {
  keys: [
    {
      id: 1,
      name: 'Console',
      masked_key: 'sk-************************************0001',
      plain_secret: 'sk-console-real-0001',
      status: 'active',
      scopes: ['admin', 'inference'],
      rpm_limit: null,
      concurrency_limit: null,
      created_at: '2026-05-15T08:00:00Z',
      disabled_at: null,
      last_used_at: null,
      note: null,
      usage_summary: {total_requests: 0, total_tokens: null},
    },
    {
      id: 2,
      name: 'CLI Admin',
      masked_key: 'sk-************************************0002',
      plain_secret: 'sk-cli-admin-real-0002',
      status: 'active',
      scopes: ['admin'],
      rpm_limit: null,
      concurrency_limit: null,
      created_at: '2026-05-15T09:00:00Z',
      disabled_at: null,
      last_used_at: null,
      note: 'created by cli',
      usage_summary: {total_requests: 0, total_tokens: null},
    },
  ],
};

const requestLogsResponse = {
  logs: [
    {
      id: 1,
      request_id: 'req-1',
      model_name: 'demo',
      status: 'ok',
      protocol: 'openai',
      error_message: null,
      created_at: '2026-05-15T08:00:00Z',
      api_key_id: null,
      auth_source: 'db',
      client_ip: '127.0.0.1',
      user_agent: 'Mozilla/5.0',
      rejection_reason: null,
      metadata: {
        client_protocol: 'chat',
        execution_mode: 'native',
        adapter_selected: null,
        tool_classes_detected: [],
        request_mutation: false,
        mutation_reason: null,
      },
    },
  ],
  total: 26,
  limit: 25,
  offset: 0,
};

const requestLogsPageTwoResponse = {
  logs: [
    {
      id: 2,
      request_id: 'req-2',
      model_name: 'demo',
      status: 'error',
      protocol: 'openai',
      error_message: 'backend down',
      created_at: '2026-05-15T09:00:00Z',
      api_key_id: null,
      auth_source: 'db',
      client_ip: '127.0.0.2',
      user_agent: 'curl/8.0',
      rejection_reason: 'backend_error',
      metadata: {
        client_protocol: 'responses',
        execution_mode: 'adapter',
        adapter_selected: 'responses_to_chat',
        tool_classes_detected: ['openai_function_tools'],
        request_mutation: true,
        mutation_reason: 'responses_to_chat',
      },
    },
  ],
  total: 26,
  limit: 25,
  offset: 25,
};

const requestLogDetailResponse = {
  request_id: 'req-1',
  log: {
    id: 1,
    request_id: 'req-1',
    model_name: 'demo',
    status: 'ok',
    protocol: 'openai',
    error_message: null,
    created_at: '2026-05-15T08:00:00Z',
    api_key_id: null,
    auth_source: 'db',
    client_ip: '127.0.0.1',
    user_agent: 'Mozilla/5.0',
    rejection_reason: null,
    metadata: {
      client_protocol: 'chat',
      execution_mode: 'native',
      adapter_selected: null,
      tool_classes_detected: [],
      request_mutation: false,
      mutation_reason: null,
    },
  },
  metrics: {
    request_id: 'req-1',
    model_name: 'demo',
    protocol: 'openai',
    status: 'ok',
    latency_ms: 1000,
    prompt_tokens: 10,
    completion_tokens: 20,
    total_tokens: 30,
    tokens_per_second: 20,
    started_at: '2026-05-15T08:00:00Z',
    finished_at: '2026-05-15T08:00:01Z',
    backend_type: 'vllm',
    api_key_id: null,
    cache_creation_tokens: 1,
    cache_read_tokens: 2,
    cache_miss_tokens: 3,
    error_code: null,
    status_detail: 'completed',
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

function textResponse(body: string, contentType = 'text/csv') {
  return Promise.resolve(
    new Response(body, {
      status: 200,
      headers: {'Content-Type': contentType},
    }),
  );
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes('/admin/status')) {
      return jsonResponse(emptySnapshot);
    }
    if (url.includes('/admin/request-logs')) {
      if (url.includes('/admin/request-logs/req-1')) {
        return jsonResponse(requestLogDetailResponse);
      }
      if (url.includes('/admin/request-logs/export')) {
        return textResponse('id,request_id\n2,req-2\n');
      }
      if (url.includes('offset=25')) {
        return jsonResponse(requestLogsPageTwoResponse);
      }
      return jsonResponse(requestLogsResponse);
    }
    if (url.includes('/admin/overview/usage')) {
      return jsonResponse(usageOverview);
    }
    if (url.includes('/admin/keys') && init?.method === 'POST') {
      return jsonResponse({
        key: {
          ...keyListResponse.keys[0],
          id: 3,
          name: 'Web Console',
          masked_key: 'sk-************************************0003',
        },
        secret: 'sk-abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd',
      });
    }
    if (url.includes('/admin/keys')) {
      return jsonResponse(keyListResponse);
    }
    if (url.includes('/admin/models')) {
      return jsonResponse({models: []});
    }
    if (url.includes('/admin/schedule')) {
      return jsonResponse({schedule: emptySnapshot.runtime.schedule});
    }
    if (url.includes('/admin/overview/readiness')) {
      return jsonResponse({
        readiness: {status: 'ready'},
        base_urls: {
          local: 'http://127.0.0.1:4000',
          lan: 'http://10.18.90.100:4000',
        },
      });
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
  });
  vi.stubGlobal(
    'fetch',
    fetchMock,
  );
  vi.stubGlobal('navigator', {
    ...navigator,
    clipboard: {
      writeText: vi.fn().mockResolvedValue(undefined),
    },
  });
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn().mockReturnValue('blob:mock'),
      revokeObjectURL: vi.fn(),
    }),
  );
});

it('shows loading state before first snapshot resolves instead of degraded', async () => {
  let releaseSnapshot: (() => void) | null = null;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        return new Promise<Response>((resolve) => {
          releaseSnapshot = () => resolve(new Response(JSON.stringify(emptySnapshot), {
            status: 200,
            headers: {'Content-Type': 'application/json'},
          }));
        });
      }
      if (url.includes('/admin/request-logs')) {
        return jsonResponse(requestLogsResponse);
      }
      if (url.includes('/admin/overview/usage')) {
        return jsonResponse(usageOverview);
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse(keyListResponse);
      }
      if (url.includes('/admin/models')) {
        return jsonResponse({models: emptySnapshot.runtime.model_routes});
      }
      if (url.includes('/admin/schedule')) {
        return jsonResponse({schedule: emptySnapshot.runtime.schedule});
      }
      if (url.includes('/admin/overview/readiness')) {
        return jsonResponse({
          readiness: {status: 'ready'},
          base_urls: {
            local: 'http://127.0.0.1:4000',
            lan: 'http://10.18.90.100:4000',
          },
        });
      }
      if (url.includes('/admin/stream')) {
        return Promise.resolve(new Response(null, {status: 503}));
      }
      return jsonResponse({});
    }),
  );

  render(<App />);
  expect(await screen.findByText('加载中')).toBeInTheDocument();
  expect(screen.queryByText('降级')).not.toBeInTheDocument();

  releaseSnapshot?.();
  await screen.findByText('健康');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('Console views', () => {
  it('shows enabled model names in overview and hides removed usage cards', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('当前可访问模型')).toBeInTheDocument();
    });

    expect(screen.getByText('qwen36-27b-fp8')).toBeInTheDocument();
    expect(screen.getByText('qwen36-35b-a3b-fp8')).toBeInTheDocument();
    expect(screen.getAllByTitle('复制模型名').length).toBe(3);
    expect(screen.getByText('路由治理')).toBeInTheDocument();
    expect(screen.getByText('1 条 stale route 待处理')).toBeInTheDocument();
    expect(screen.getByText('1 条 manual route 已接管')).toBeInTheDocument();
    expect(screen.getByText('3 条 profile seed route')).toBeInTheDocument();
    expect(screen.queryByText('每日 Token 用量')).not.toBeInTheDocument();
    expect(screen.queryByText('后端用量分布')).not.toBeInTheDocument();
  });

  it('shows copy success toast after copying a model name', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('当前可访问模型')).toBeInTheDocument();
    });

    await userEvent.click(screen.getAllByTitle('复制模型名')[0]);

    expect(await screen.findByText('已复制到剪贴板')).toBeInTheDocument();
    expect(screen.getByTestId('copy-toast')).toHaveClass('opacity-100');
  });

  it('does not show generated secret success panel after creating a key', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('密钥管理')[0]);
    await userEvent.click(screen.getByRole('button', {name: '创建密钥'}));

    await waitFor(() => {
      expect(screen.queryByText('密钥生成成功')).not.toBeInTheDocument();
      expect(screen.queryByText('请立刻保存这个密钥。关闭后将无法再次查看。')).not.toBeInTheDocument();
      expect(screen.getByText('sk-************************************0002')).toBeInTheDocument();
    });

    const createdRow = screen.getByText('Web Console').closest('tr');
    expect(createdRow).toBeTruthy();
    const createdScope = within(createdRow as HTMLElement);

    await userEvent.click(createdScope.getByRole('button', {name: '显示'}));
    expect(createdScope.getByText('sk-abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd')).toBeInTheDocument();
  });

  it('renders usage trend controls and records table headings', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('请求记录')[0]);

    expect(await screen.findByText('调用趋势')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: '12 小时'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: '按后端'})).toBeInTheDocument();
    expect(screen.getByText('调用记录')).toBeInTheDocument();
  });

  it('formats large numeric values with grouping and compact suffixes', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('请求记录')[0]);

    expect(await screen.findByText('12,345')).toBeInTheDocument();
    expect(screen.getByText('12.35M')).toBeInTheDocument();
    expect(screen.getByText('3.46B')).toBeInTheDocument();
  });

  it('requests request logs with pagination and date filters', async () => {
    vi.setSystemTime(new Date('2026-05-19T17:42:00+08:00'));
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('请求记录')[0]);

    const fromInput = await screen.findByLabelText('开始时间');
    const toInput = screen.getByLabelText('结束时间');
    await userEvent.clear(fromInput);
    await userEvent.type(fromInput, '2026-05-15T00:00');
    await userEvent.clear(toInput);
    await userEvent.type(toInput, '2026-05-15T23:59');
    await userEvent.click(screen.getByRole('button', {name: '应用时间'}));

    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes('/admin/request-logs?limit=25&offset=0') && url.includes('date_from=2026-05-14T16%3A00%3A00Z') && url.includes('date_to=2026-05-15T15%3A59%3A00Z'))).toBe(true);
    });
  });

  it('supports jump-to-page and export csv on usage records', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('请求记录')[0]);
    await userEvent.clear(await screen.findByLabelText('跳到页'));
    await userEvent.type(screen.getByLabelText('跳到页'), '2');
    await userEvent.click(screen.getByRole('button', {name: '跳转'}));

    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes('/admin/request-logs?') && url.includes('limit=25') && url.includes('offset=25'))).toBe(true);
    });

    await userEvent.click(screen.getByRole('button', {name: '导出 CSV'}));

    await waitFor(() => {
      const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes('/admin/request-logs/export'))).toBe(true);
    });
  });

  it('opens request detail drawer with metrics', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('请求记录')[0]);
    await userEvent.click(await screen.findByText('req-1'));

    const drawer = await screen.findByTestId('request-detail-drawer');
    expect(within(drawer).getByText('请求详情')).toBeInTheDocument();
    expect(within(drawer).getByText('demo')).toBeInTheDocument();
    expect(within(drawer).getByText('vllm')).toBeInTheDocument();
    expect(within(drawer).getByText('30')).toBeInTheDocument();
  });

  it('submits extended external route payload for manual route from models view', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        return jsonResponse(emptySnapshot);
      }
      if (url.includes('/admin/request-logs')) {
        return jsonResponse(requestLogsResponse);
      }
      if (url.includes('/admin/overview/usage')) {
        return jsonResponse(usageOverview);
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse(keyListResponse);
      }
      if (url.includes('/admin/models/anthropic-claude') && init?.method === 'DELETE') {
        return jsonResponse({deleted: true, name: 'anthropic-claude'});
      }
      if (url.includes('/admin/models/anthropic-claude') && init?.method === 'PATCH') {
        const payload = JSON.parse(String(init.body));
        return jsonResponse({
          model: {
            name: 'anthropic-claude',
            display_name: payload.display_name,
            backend_model: payload.backend_model,
            backend_type: payload.backend_type,
            enabled: payload.enabled,
            lifecycle_mode: payload.lifecycle_mode,
            upstream_protocol: payload.upstream_protocol,
            upstream_base_url: payload.upstream_base_url,
            upstream_model: payload.upstream_model,
            upstream_auth_kind: payload.upstream_auth_kind,
            upstream_auth_ref: payload.upstream_auth_ref,
            source_kind: 'manual',
            source_ref: null,
            stale: false,
            capabilities_json: payload.capabilities_json,
            native_protocols_json: payload.native_protocols_json,
            adapter_policies_json: payload.adapter_policies_json,
            tool_policies_json: payload.tool_policies_json,
            protocol_features_json: payload.protocol_features_json,
          },
        });
      }
      if (url.includes('/admin/models')) {
        return jsonResponse({models: emptySnapshot.runtime.model_routes});
      }
      if (url.includes('/admin/schedule')) {
        return jsonResponse({schedule: emptySnapshot.runtime.schedule});
      }
      if (url.includes('/admin/overview/readiness')) {
        return jsonResponse({
          readiness: {status: 'ready'},
          base_urls: {
            local: 'http://127.0.0.1:4000',
            lan: 'http://10.18.90.100:4000',
          },
        });
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
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    const row = await screen.findByText('anthropic-claude');
    expect(row).toBeInTheDocument();
    const routeCard = row.closest('section');
    expect(routeCard).toBeTruthy();
    const routeScope = within(routeCard as HTMLElement);

    const displayInput = routeScope.getByText('显示名称').parentElement?.querySelector('input');
    expect(displayInput).toBeTruthy();
    await userEvent.clear(displayInput as HTMLInputElement);
    await userEvent.type(displayInput as HTMLInputElement, 'External GPT Route');

    const upstreamBaseInput = routeScope.getByText('上游地址').parentElement?.querySelector('input');
    expect(upstreamBaseInput).toBeTruthy();
    await userEvent.clear(upstreamBaseInput as HTMLInputElement);
    await userEvent.type(upstreamBaseInput as HTMLInputElement, 'https://api.openai.com/v1');

    const upstreamModelInput = routeScope.getByText('上游模型名').parentElement?.querySelector('input');
    expect(upstreamModelInput).toBeTruthy();
    await userEvent.clear(upstreamModelInput as HTMLInputElement);
    await userEvent.type(upstreamModelInput as HTMLInputElement, 'gpt-4o');

    const protocolSelect = routeScope.getByText('上游协议').parentElement?.querySelector('select');
    expect(protocolSelect).toBeTruthy();
    await userEvent.selectOptions(protocolSelect as HTMLSelectElement, 'responses');

    const authSelect = routeScope.getByText('鉴权方式').parentElement?.querySelector('select');
    expect(authSelect).toBeTruthy();
    await userEvent.selectOptions(authSelect as HTMLSelectElement, 'bearer');

    const supportResponses = routeScope.getByRole('checkbox', {name: 'Responses'});
    if (!supportResponses.hasAttribute('checked')) {
      await userEvent.click(supportResponses);
    }
    const supportBuiltinTools = routeScope.getByRole('checkbox', {name: 'Builtin Tools'});
    await userEvent.click(supportBuiltinTools);
    const supportPrevResp = routeScope.getByRole('checkbox', {name: 'Previous Response'});
    await userEvent.click(supportPrevResp);
    const supportSchema = routeScope.getByRole('checkbox', {name: 'JSON Schema'});
    await userEvent.click(supportSchema);

    await userEvent.click(routeScope.getByRole('button', {name: '保存'}));

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        (call) => String(call[0]).includes('/admin/models/anthropic-claude') && call[1]?.method === 'PATCH',
      );
      expect(patchCall).toBeTruthy();
      const payload = JSON.parse(String(patchCall?.[1]?.body));
      expect(payload).toMatchObject({
        display_name: 'External GPT Route',
        lifecycle_mode: 'external',
        upstream_protocol: 'responses',
        upstream_base_url: 'https://api.openai.com/v1',
        upstream_model: 'gpt-4o',
        upstream_auth_kind: 'bearer',
      });
      expect(payload.capabilities_json).toMatchObject({
        supports_responses: true,
        supports_builtin_tools: true,
        supports_previous_response_id_native: true,
        supports_json_schema: true,
      });
      expect(payload.native_protocols_json).toEqual(['responses']);
      expect(payload.adapter_policies_json).toEqual([]);
      expect(payload.tool_policies_json).toMatchObject({
        anthropic_function_tools: true,
        builtin_tools: false,
      });
      expect(payload.protocol_features_json).toMatchObject({
        stream: true,
        count_tokens: false,
      });
    });
  });

  it('shows route source badges and delete action for manual routes', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    expect((await screen.findAllByText('Profile Seed')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('Manual')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', {name: 'Delete anthropic-claude'})).toBeInTheDocument();
  });

  it('shows stale profile route guidance and blocks profile seed lifecycle conversion in ui', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    expect(await screen.findByText('legacy-qwen-route')).toBeInTheDocument();
    expect(screen.getByText('当前 profile 不再提供这条 route；系统已自动禁用，需由你决定是否保留。')).toBeInTheDocument();
    expect(screen.getByText('来源 profile: vllm_qwen36-14b-legacy')).toBeInTheDocument();

    const staleRoute = await screen.findByText('legacy-qwen-route');
    const staleCard = staleRoute.closest('section');
    expect(staleCard).toBeTruthy();
    const staleEnabledToggle = within(staleCard as HTMLElement).getByLabelText('legacy-qwen-route-enabled');
    expect(staleEnabledToggle).toBeDisabled();
    expect(within(staleCard as HTMLElement).getByText('Stale 的 Profile Seed route 当前不能直接重新启用；如需恢复，请切回来源 profile 或新建 manual route。')).toBeInTheDocument();
    expect(
      within(staleCard as HTMLElement).getByText(
        '当前允许：保留禁用态观察、查看来源 profile、调整展示字段；当前不允许：直接重新启用、删除、改成 external。',
      ),
    ).toBeInTheDocument();

    const seededRoute = await screen.findByText('qwen36-27b-fp8');
    const seededCard = seededRoute.closest('section');
    expect(seededCard).toBeTruthy();
    const lifecycleSelect = within(seededCard as HTMLElement).getByText('生命周期').parentElement?.querySelector('select');
    expect(lifecycleSelect).toBeDisabled();
    expect(within(seededCard as HTMLElement).getByText('Profile Seed route 当前不能直接改成 external；如需外部上游，请新建 manual route。')).toBeInTheDocument();
  });

  it('creates external routes from models view', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    const runtimeModelRoutes = cloneJson(emptySnapshot.runtime.model_routes);
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        const snapshot = cloneJson(emptySnapshot);
        snapshot.runtime.model_routes = runtimeModelRoutes;
        return jsonResponse(snapshot);
      }
      if (url.includes('/admin/request-logs')) {
        return jsonResponse(requestLogsResponse);
      }
      if (url.includes('/admin/overview/usage')) {
        return jsonResponse(usageOverview);
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse(keyListResponse);
      }
      if (url.includes('/admin/models') && init?.method === 'POST') {
        const payload = JSON.parse(String(init.body));
        const createdRoute = {
          name: payload.name,
          display_name: payload.display_name,
          backend_model: null,
          backend_type: null,
          enabled: payload.enabled,
          lifecycle_mode: 'external',
          upstream_protocol: payload.upstream_protocol,
          upstream_base_url: payload.upstream_base_url,
          upstream_model: payload.upstream_model,
          upstream_auth_kind: payload.upstream_auth_kind,
          upstream_auth_ref: payload.upstream_auth_ref,
          source_kind: 'manual',
          source_ref: null,
          stale: false,
          capabilities_json: payload.capabilities_json,
          native_protocols_json: payload.native_protocols_json ?? [payload.upstream_protocol],
          adapter_policies_json: payload.adapter_policies_json ?? [],
          tool_policies_json: payload.tool_policies_json ?? {
            openai_function_tools: true,
            anthropic_function_tools: true,
            builtin_tools: false,
          },
          protocol_features_json: payload.protocol_features_json ?? {
            stream: true,
            count_tokens: payload.upstream_protocol === 'messages',
            json_schema: false,
            previous_response_id: false,
          },
        };
        runtimeModelRoutes.push(createdRoute);
        return jsonResponse({model: createdRoute});
      }
      if (url.includes('/admin/models')) {
        return jsonResponse({models: runtimeModelRoutes});
      }
      if (url.includes('/admin/schedule')) {
        return jsonResponse({schedule: emptySnapshot.runtime.schedule});
      }
      if (url.includes('/admin/overview/readiness')) {
        return jsonResponse({
          readiness: {status: 'ready'},
          base_urls: {
            local: 'http://127.0.0.1:4000',
            lan: 'http://10.18.90.100:4000',
          },
        });
      }
      if (url.includes('/admin/stream')) {
        const stream = new ReadableStream({
          start(controller) {
            const snapshot = cloneJson(emptySnapshot);
            snapshot.runtime.model_routes = runtimeModelRoutes;
            controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(snapshot)}\n\n`));
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
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    await userEvent.type(await screen.findByLabelText('create-route-name'), 'openai-gpt-4o');
    await userEvent.type(screen.getByLabelText('create-route-display-name'), 'OpenAI GPT-4o');
    await userEvent.selectOptions(screen.getByLabelText('create-route-protocol'), 'responses');
    await userEvent.type(screen.getByLabelText('create-route-base-url'), 'https://api.openai.com/v1');
    await userEvent.type(screen.getByLabelText('create-route-upstream-model'), 'gpt-4o');
    await userEvent.selectOptions(screen.getByLabelText('create-route-auth-kind'), 'bearer');
    await userEvent.type(screen.getByLabelText('create-route-auth-ref'), 'OPENAI_API_KEY');
    await userEvent.click(screen.getByRole('checkbox', {name: 'create-route-supports-responses'}));

    await userEvent.click(screen.getByRole('button', {name: '创建路由'}));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        (call) => String(call[0]).includes('/admin/models') && call[1]?.method === 'POST',
      );
      expect(postCall).toBeTruthy();
      const payload = JSON.parse(String(postCall?.[1]?.body));
      expect(payload).toMatchObject({
        name: 'openai-gpt-4o',
        display_name: 'OpenAI GPT-4o',
        lifecycle_mode: 'external',
        upstream_protocol: 'responses',
        upstream_base_url: 'https://api.openai.com/v1',
        upstream_model: 'gpt-4o',
        upstream_auth_kind: 'bearer',
        upstream_auth_ref: 'OPENAI_API_KEY',
        enabled: true,
      });
      expect(payload.capabilities_json.supports_responses).toBe(true);
      expect(payload.native_protocols_json).toEqual(['responses']);
    });

    expect(await screen.findByText('openai-gpt-4o')).toBeInTheDocument();
    expect(screen.getByDisplayValue('OpenAI GPT-4o')).toBeInTheDocument();
  });

  it('shows cli-created keys from admin list', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('密钥管理')[0]);

    expect(await screen.findByText('CLI Admin')).toBeInTheDocument();
    expect(screen.getByText('created by cli')).toBeInTheDocument();
    expect(screen.getByText('sk-************************************0002')).toBeInTheDocument();
  });

  it('copies real secret from key list instead of masked key', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {writeText},
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('密钥管理')[0]);
    const consoleRow = (await screen.findByText('Console')).closest('tr');
    expect(consoleRow).toBeTruthy();
    const consoleScope = within(consoleRow as HTMLElement);

    expect(consoleScope.getByText('sk-************************************0001')).toBeInTheDocument();

    await userEvent.click(consoleScope.getByRole('button', {name: '显示'}));
    expect(consoleScope.getByText('sk-console-real-0001')).toBeInTheDocument();

    const secretCopyButton = consoleScope.getByRole('button', {name: '复制真实密钥'});
    await userEvent.click(secretCopyButton);

    expect(writeText).toHaveBeenCalledWith('sk-console-real-0001');
    expect(await screen.findByText('已复制到剪贴板')).toBeInTheDocument();
    expect(screen.getByTestId('copy-toast')).toHaveClass('opacity-100');

    await userEvent.click(consoleScope.getByRole('button', {name: '隐藏'}));
    expect(consoleScope.getByText('sk-************************************0001')).toBeInTheDocument();
  });

  it('keeps api key display width fixed when toggling secret visibility', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('密钥管理')[0]);
    const secretValue = await screen.findByTestId('api-key-secret-1');

    expect(secretValue).toHaveClass('w-[36ch]');
    expect(secretValue).toHaveTextContent('sk-************************************0001');

    const consoleRow = (await screen.findByText('Console')).closest('tr');
    expect(consoleRow).toBeTruthy();
    const consoleScope = within(consoleRow as HTMLElement);

    await userEvent.click(consoleScope.getByRole('button', {name: '显示'}));
    expect(secretValue).toHaveClass('w-[36ch]');
    expect(secretValue).toHaveTextContent('sk-console-real-0001');
  });

  it('updates recommended runtime defaults when create route protocol changes', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    const createSectionHeading = await screen.findByText('新增外部路由');
    const createSection = createSectionHeading.closest('section');
    expect(createSection).toBeTruthy();
    const createScope = within(createSection as HTMLElement);

    await userEvent.selectOptions(await createScope.findByLabelText('create-route-protocol'), 'messages');

    expect(createScope.getByRole('checkbox', {name: 'create-native-protocol-messages'})).toBeChecked();
    expect(createScope.getByRole('checkbox', {name: 'create-native-protocol-chat'})).not.toBeChecked();
    expect(createScope.getByRole('checkbox', {name: 'create-native-protocol-responses'})).not.toBeChecked();
    expect(createScope.getByRole('checkbox', {name: 'create-protocol-feature-count-tokens'})).toBeChecked();
  });

  it('uses backend recommended runtime semantics when create route protocol changes', async () => {
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    const snapshotWithCustomRecommended = cloneJson(emptySnapshot);
    snapshotWithCustomRecommended.runtime.model_routes[0].recommended_runtime_semantics = {
      native_protocols_json: ['chat'],
      adapter_policies_json: ['responses->chat'],
      protocol_features_json: {
        stream: true,
        count_tokens: false,
        json_schema: false,
        previous_response_id: false,
      },
    };
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/admin/status')) {
        return jsonResponse(snapshotWithCustomRecommended);
      }
      if (url.includes('/admin/request-logs')) {
        return jsonResponse(requestLogsResponse);
      }
      if (url.includes('/admin/overview/usage')) {
        return jsonResponse(usageOverview);
      }
      if (url.includes('/admin/keys')) {
        return jsonResponse(keyListResponse);
      }
      if (url.includes('/admin/models')) {
        return jsonResponse({models: snapshotWithCustomRecommended.runtime.model_routes});
      }
      if (url.includes('/admin/schedule')) {
        return jsonResponse({schedule: snapshotWithCustomRecommended.runtime.schedule});
      }
      if (url.includes('/admin/overview/readiness')) {
        return jsonResponse({
          readiness: {status: 'ready'},
          base_urls: {
            local: 'http://127.0.0.1:4000',
            lan: 'http://10.18.90.100:4000',
          },
        });
      }
      if (url.includes('/admin/stream')) {
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(snapshotWithCustomRecommended)}\n\n`));
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
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    const createSectionHeading = await screen.findByText('新增外部路由');
    const createSection = createSectionHeading.closest('section');
    expect(createSection).toBeTruthy();
    const createScope = within(createSection as HTMLElement);

    await userEvent.selectOptions(await createScope.findByLabelText('create-route-protocol'), 'chat');

    expect(createScope.getByRole('checkbox', {name: 'create-native-protocol-chat'})).toBeChecked();
    expect(createScope.getByRole('checkbox', {name: 'create-native-protocol-responses'})).not.toBeChecked();
    expect(createScope.getByRole('checkbox', {name: 'create-adapter-policy-responses-chat'})).toBeChecked();
  });

  it('shows runtime warning and can apply recommended defaults for manual route', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText('LlmNode').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getAllByText('模型路由')[0]);

    const row = await screen.findByText('anthropic-claude');
    const routeCard = row.closest('section');
    expect(routeCard).toBeTruthy();
    const routeScope = within(routeCard as HTMLElement);

    await userEvent.click(routeScope.getByRole('checkbox', {name: 'anthropic-claude-native-protocol-chat'}));

    expect(routeScope.getByRole('button', {name: '恢复推荐默认'})).toBeInTheDocument();

    await userEvent.click(routeScope.getByRole('button', {name: '恢复推荐默认'}));

    expect(routeScope.getByRole('checkbox', {name: 'anthropic-claude-native-protocol-messages'})).toBeChecked();
    expect(routeScope.getByRole('checkbox', {name: 'anthropic-claude-native-protocol-chat'})).not.toBeChecked();
    expect(routeScope.queryByRole('button', {name: '恢复推荐默认'})).not.toBeInTheDocument();
  });
});
