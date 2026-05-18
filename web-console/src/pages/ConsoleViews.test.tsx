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
      },
    ],
  },
};

const usageOverview = {
  summary: {
    request_count: 1,
    success_count: 1,
    success_rate: 1,
    avg_latency_ms: 10,
    p95_latency_ms: 10,
    p99_latency_ms: 10,
    throughput_tokens_per_s: 50,
    tokens_observed_requests: 1,
    total_tokens: 42,
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
          prompt_tokens: 10,
          completion_tokens: 20,
          cache_creation_tokens: 5,
          cache_read_tokens: 7,
          cache_miss_tokens: 2,
          cache_tokens: 14,
          total_tokens: 42,
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
      status: 'active',
      scopes: ['admin', 'inference'],
      rpm_limit: null,
      concurrency_limit: null,
      created_at: '2026-05-15 08:00:00',
      disabled_at: null,
      last_used_at: null,
      note: null,
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

beforeEach(() => {
  window.localStorage.setItem('vllm-console-api-key', 'sk-test-console');
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
          id: 2,
          masked_key: 'sk-************************************0002',
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
    expect(screen.getAllByTitle('复制模型名').length).toBe(2);
    expect(screen.queryByText('每日 Token 用量')).not.toBeInTheDocument();
    expect(screen.queryByText('后端用量分布')).not.toBeInTheDocument();
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
      expect(screen.getByText('sk-abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd')).toBeInTheDocument();
    });
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

  it('requests request logs with pagination and date filters', async () => {
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
      expect(calls.some((url) => url.includes('/admin/request-logs?limit=25&offset=0') && url.includes('date_from=2026-05-15T00%3A00') && url.includes('date_to=2026-05-15T23%3A59'))).toBe(true);
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

  it('submits extended external route payload from models view', async () => {
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
      if (url.includes('/admin/models') && init?.method === 'PATCH') {
        const payload = JSON.parse(String(init.body));
        return jsonResponse({
          model: {
            name: 'qwen36-27b-fp8',
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
            capabilities_json: payload.capabilities_json,
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

    const row = await screen.findByText('qwen36-27b-fp8');
    expect(row).toBeInTheDocument();

    const displayInputs = screen.getAllByDisplayValue('Qwen 27B FP8');
    await userEvent.clear(displayInputs[0]);
    await userEvent.type(displayInputs[0], 'External GPT Route');

    const upstreamBaseInput = screen.getAllByDisplayValue('http://127.0.0.1:8000/v1')[0];
    await userEvent.clear(upstreamBaseInput);
    await userEvent.type(upstreamBaseInput, 'https://api.openai.com/v1');

    const upstreamModelInput = screen.getAllByDisplayValue('Qwen/Qwen3.6-27B-FP8')[1];
    await userEvent.clear(upstreamModelInput);
    await userEvent.type(upstreamModelInput, 'gpt-4o');

    await userEvent.selectOptions(screen.getAllByRole('combobox')[0], 'external');
    await userEvent.selectOptions(screen.getAllByRole('combobox')[1], 'responses');
    await userEvent.selectOptions(screen.getAllByRole('combobox')[3], 'bearer');

    const supportResponses = screen.getAllByRole('checkbox', {name: 'Responses'})[0];
    if (!supportResponses.hasAttribute('checked')) {
      await userEvent.click(supportResponses);
    }
    const supportBuiltinTools = screen.getAllByRole('checkbox', {name: 'Builtin Tools'})[0];
    await userEvent.click(supportBuiltinTools);
    const supportPrevResp = screen.getAllByRole('checkbox', {name: 'Previous Response'})[0];
    await userEvent.click(supportPrevResp);
    const supportSchema = screen.getAllByRole('checkbox', {name: 'JSON Schema'})[0];
    await userEvent.click(supportSchema);

    await userEvent.click(screen.getAllByRole('button', {name: '保存'})[0]);

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        (call) => String(call[0]).includes('/admin/models/qwen36-27b-fp8') && call[1]?.method === 'PATCH',
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
    });
  });
});
