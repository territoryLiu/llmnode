import { createRouter, createWebHistory } from 'vue-router'

import ConsoleLayout from '@/layouts/ConsoleLayout.vue'
import ApiKeysView from '@/views/ApiKeysView.vue'
import ModelRoutesView from '@/views/ModelRoutesView.vue'
import OverviewView from '@/views/OverviewView.vue'
import ScheduleView from '@/views/ScheduleView.vue'
import SystemStatusView from '@/views/SystemStatusView.vue'
import UsageRecordsView from '@/views/UsageRecordsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: ConsoleLayout,
      children: [
        {
          path: '',
          name: 'overview',
          component: OverviewView,
          meta: {
            title: '仪表盘',
            subtitle: '欢迎回来，这是本机网关的总览面板。',
          },
        },
        {
          path: 'usage',
          name: 'usage',
          component: UsageRecordsView,
          meta: {
            title: '使用记录',
            subtitle: '查看和分析 API 请求、SSE 状态与审计日志。',
          },
        },
        {
          path: 'keys',
          name: 'keys',
          component: ApiKeysView,
          meta: {
            title: 'API 密钥',
            subtitle: '管理网关访问密钥、状态与配额。',
          },
        },
        {
          path: 'models',
          name: 'models',
          component: ModelRoutesView,
          meta: {
            title: '模型路由',
            subtitle: '查看逻辑模型与后端映射，当前仅支持 vLLM。',
          },
        },
        {
          path: 'schedule',
          name: 'schedule',
          component: ScheduleView,
          meta: {
            title: '调度设置',
            subtitle: '工作时段、自动启停与恢复策略。',
          },
        },
        {
          path: 'status',
          name: 'status',
          component: SystemStatusView,
          meta: {
            title: '系统状态',
            subtitle: '查看节点代理、队列、恢复和运行事件。',
          },
        },
      ],
    },
  ],
})
