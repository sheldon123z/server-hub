/**
 * 全局 AI 对话气泡组件 — Alpine.js
 * 复用 /api/agents/chat SSE 端点，注入页面上下文
 */
function chatWidget() {
  return {
    // 面板状态
    isOpen: false,
    isMinimized: false,

    // 位置与尺寸（localStorage 持久化）
    panelRight: 24,
    panelBottom: 24,
    panelWidth: 400,
    panelHeight: 500,

    // 对话状态
    messages: [],
    inputText: '',
    isTyping: false,
    conversationId: null,
    todos: [],
    todoCollapsed: true,
    safetyMode: 'supervised',

    // 页面上下文（由 Jinja2 注入）
    pageContext: '',
    pageLabel: '',

    // 拖拽
    _dragStart: null,
    _resizeStart: null,

    init() {
      this.loadLayout();
      // pageContext 和 pageLabel 由 HTML 属性传入
    },

    // ─── 布局持久化 ───
    loadLayout() {
      try {
        const saved = JSON.parse(localStorage.getItem('cw-layout'));
        if (saved) {
          this.panelRight = saved.right ?? 24;
          this.panelBottom = saved.bottom ?? 24;
          this.panelWidth = saved.width ?? 400;
          this.panelHeight = saved.height ?? 500;
        }
      } catch(e) {}
    },
    saveLayout() {
      localStorage.setItem('cw-layout', JSON.stringify({
        right: this.panelRight, bottom: this.panelBottom,
        width: this.panelWidth, height: this.panelHeight,
      }));
    },

    get panelStyle() {
      const base = `right:${this.panelRight}px;bottom:${this.panelBottom}px;width:${this.panelWidth}px;`;
      // 最小化时不设固定高度，让面板自适应（仅显示标题栏）
      return this.isMinimized ? base : base + `height:${this.panelHeight}px;`;
    },

    // ─── 拖拽 ───
    // 面板使用 right+bottom 定位，数值方向与鼠标运动相反
    startDrag(e) {
      if (e.target.closest('button')) return;
      this._dragStart = { x: e.clientX, y: e.clientY, r: this.panelRight, b: this.panelBottom };
      const onMove = (ev) => {
        const dx = ev.clientX - this._dragStart.x;
        const dy = ev.clientY - this._dragStart.y;
        // 鼠标右移 → right 减小（面板右移）；鼠标下移 → bottom 减小（面板下移）
        this.panelRight = Math.max(0, this._dragStart.r - dx);
        this.panelBottom = Math.max(0, this._dragStart.b - dy);
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        this.saveLayout();
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    startResize(e) {
      e.preventDefault();
      this._resizeStart = { x: e.clientX, y: e.clientY, w: this.panelWidth, h: this.panelHeight };
      const onMove = (ev) => {
        const dx = this._resizeStart.x - ev.clientX;
        const dy = this._resizeStart.y - ev.clientY;
        this.panelWidth = Math.max(320, this._resizeStart.w + dx);
        this.panelHeight = Math.max(300, this._resizeStart.h + dy);
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        this.saveLayout();
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    // ─── 消息发送 ───
    async sendMessage() {
      const text = this.inputText.trim();
      if (!text || this.isTyping) return;
      this.inputText = '';
      this.messages.push({ role: 'user', content: text });
      this.isTyping = true;
      this.scrollBottom();

      try {
        const resp = await fetch('/api/agents/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            conversation_id: this.conversationId,
            safety_mode: this.safetyMode,
            page_context: this.pageContext || null,
          }),
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', currentEvent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              try {
                this.handleSSE(currentEvent, JSON.parse(line.slice(5).trim()));
              } catch(e) {}
            }
          }
        }
      } catch(e) {
        this.messages.push({ role: 'assistant', content: '连接错误: ' + e.message });
      }

      this.isTyping = false;
      this.scrollBottom();
    },

    // ─── SSE 事件处理 ───
    handleSSE(event, data) {
      switch(event) {
        case 'message':
          this.messages.push({ role: 'assistant', content: data.content });
          break;
        case 'tool_call':
          this.messages.push({ role: 'tool_call', tool: data.tool, args: data.input });
          break;
        case 'tool_result':
          this.messages.push({ role: 'tool_result', tool: data.tool || '', content: data.content });
          break;
        case 'todo_update':
          this.todos = Array.isArray(data) ? data : [];
          this.todoCollapsed = false;
          break;
        case 'approval_request':
          this.messages.push({
            role: 'approval',
            approval_id: data.approval_id,
            actions: data.actions,
            description: data.description || (data.actions ? data.actions.map(a => a.name).join(', ') : '需要确认'),
          });
          break;
        case 'done':
          if (data.conversation_id) this.conversationId = data.conversation_id;
          break;
        case 'error':
          this.messages.push({ role: 'assistant', content: '错误: ' + (data.error || '未知') });
          break;
      }
      this.scrollBottom();
    },

    // ─── 审批 ───
    async resolveApproval(approvalId, action) {
      try {
        const resp = await fetch(`/api/agents/approvals/${approvalId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        });
        const d = await resp.json();
        if (d.ok && action === 'approve' && d.result) {
          this.messages.push({ role: 'assistant', content: d.result });
        } else if (action === 'reject') {
          this.messages.push({ role: 'assistant', content: '操作已被拒绝。' });
        }
      } catch(e) {
        this.messages.push({ role: 'assistant', content: '审批处理失败: ' + e.message });
      }
    },

    // ─── Markdown 渲染（轻量） ───
    renderMd(text) {
      if (!text) return '';
      return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n- /g, '\n• ')
        .replace(/\n/g, '<br>');
    },

    // ─── 新对话 ───
    newConversation() {
      this.messages = [];
      this.conversationId = null;
      this.todos = [];
    },

    scrollBottom() {
      this.$nextTick(() => {
        const el = document.getElementById('cw-messages');
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
  };
}
