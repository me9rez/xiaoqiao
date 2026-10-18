import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import MessageItem from '@/components/chat/MessageItem.vue'

describe('MessageItem', () => {
  beforeEach(() => {
    // The component exposes a 引用 action that writes to the chat store.
    setActivePinia(createPinia())
  })

  it('renders user message', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '1',
          role: 'user',
          content: 'Hello',
          timestamp: Date.now(),
        },
      },
    })
    expect(wrapper.text()).toContain('Hello')
  })

  it('renders assistant markdown', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '2',
          role: 'assistant',
          content: '# Title',
          timestamp: Date.now(),
        },
      },
    })
    expect(wrapper.html()).toContain('<h1')
  })

  it('renders tool call block', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '3',
          role: 'tool',
          content: '',
          timestamp: Date.now(),
          toolCall: { callId: 'c1', name: 'run_command', arguments: '{"command":"ls"}' },
          toolExecution: { callId: 'c1', name: 'run_command', output: 'file.txt', ok: true, exitCode: 0 },
        },
      },
    })
    expect(wrapper.text()).toContain('run_command')
    expect(wrapper.text()).toContain('成功')
  })
})
