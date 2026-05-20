# Frontend Design Document

> **Document Version**: v1.0
> **Created**: 2026-04-22
> **Last Updated**: 2026-04-22

---

## Project Repository

- **Frontend**: `D:\Coding\GitHub_Resuorse\emotion-robot\atri-webui`
- **Backend**: `D:\Coding\GitHub_Resuorse\emotion-robot\atri`

## Reference Documents

- **Design Discussion**: `docs/总结_前端对话历史.md` (Round 1-18)
- **Full Conversation**: `docs/前端设计对话历史.md`
- **Backend Architecture**: `docs/后端设计.md`
- **Backend API**: `docs/后端API接口文档.md`
- **Feature Comparison**: `docs/projects-docs/AIRI与atri功能对比分析.md`
- **AIRI Feature List**: `docs/projects-docs/AIRI前端功能清单.md`

## Reference Projects

- **AIRI Architecture**: `docs/projects-docs/airi_架构文档.md`
- **AIRI Source Code**: `refer-projects/airi/`
- **AIRI stage-ui**: `airi/packages/stage-ui/` (UI component reuse)
- **AIRI ui**: `airi/packages/ui/` (base component reuse)
- **AIRI stage-web**: `airi/packages/stage-web/` (main page layout reference)

## Related Module Design Documents

- **ASR Module**: `docs/ASR模块设计文档.md`
- **TTS Module**: `docs/TTS模块设计文档.md`
- **Live2D Module**: `docs/Live-2d设计文档.md`



> **Note**: All code examples in this document are pseudocode (interface/implementation examples)

---

## 1. Module Overview

### 1.1 Frontend Positioning and Responsibilities

atri-webui is the web frontend of the atri project, adopting a **centralized architecture**: the backend manages all Provider configurations and API Keys, while the frontend is only responsible for user interaction and data display.

**Core Responsibilities**:
- Provide a chat interface with real-time streaming dialogue (WebSocket)
- Provide character selection and chat history management
- Provide 11 settings pages to manage configuration for each module
- Integrate Live2D model rendering and expression control
- Provide personalization features such as background customization and theme switching

**Architecture Principles**:
- **Backend manages configuration**: LLM/TTS/ASR Provider configurations and API Keys are stored in backend YAML; the frontend only selects from them (read-only)
- **Frontend manages preferences**: UI preferences, background settings, Live2D toggle are stored in frontend LocalStorage
- **Full AIRI UI reuse**: UI components and CSS styles are directly reused from AIRI, with no custom style adjustments

### 1.2 Core Feature List

1. **Chat Interface**: Streaming message display, character selection, history conversation switching
2. **Dual-mode Main Page**: ChatGPT style when Live2D is off, AIRI style when Live2D is on
3. **Character Management**: Character card CRUD (create/edit/delete/import/export)
4. **Settings System**: 11 settings pages covering all module configurations
5. **Background Customization**: Image upload, opacity/blur adjustment
6. **Live2D Integration**: Model rendering, expression control, model management
7. **Authentication System**: GitHub OAuth + whitelist mode
8. **Data Management**: Export/import/clear chat history and memory data
9. **Responsive Design**: Support for desktop, tablet, and mobile

### 1.3 Design Goals

- **Zero CSS adjustments**: UI components and styles fully reuse AIRI, no time spent adjusting CSS
- **Real-time communication**: WebSocket streaming dialogue with exponential backoff reconnection
- **Responsive**: Mobile support (sm/md/lg breakpoints)
- **Easy integration**: RESTful API + WebSocket, decoupled from backend
- **Extensible**: Component-based design, easy to add new features

### 1.4 Core Differences from AIRI

atri's frontend is functionally similar to AIRI's frontend, but has the following key differences:

#### Difference 1: Dual-mode Main Page

| Mode | Trigger Condition | Layout Style | Style Source |
|------|------------------|--------------|--------------|
| **Mode A: ChatGPT Style** | Live2D disabled | Sidebar + Chat Area | Agent uses `/frontend-design` skill to implement in AIRI style |
| **Mode B: AIRI Style** | Live2D enabled | Live2D model + floating chat box | Directly reuse AIRI implementation |

**Mode A (Live2D disabled)**:
```
┌─────────────────────────────────────┐
│  Sidebar  │  Chat Area              │
│           │                         │
│  Character│  Message List           │
│  History  │                         │
│           │  Input Box              │
└─────────────────────────────────────┘
```
- ChatGPT-like title/history conversation style
- Example already implemented in `atri-webui/src/`
- Styles need to be implemented by agent using `/frontend-design` skill in AIRI style

**Mode B (Live2D enabled)**:
```
┌─────────────────────────────────────┐
│  [Fold Panel]     Live2D Model      │
│                                     │
│                                     │
│              ┌──────────────┐       │
│              │  Chat Box    │       │
│              │  Input Box   │       │
│              └──────────────┘       │
└─────────────────────────────────────┘
```
- Fully reuse AIRI's main page layout
- Add a fold panel component in the top-left corner

#### Difference 2: Fold Panel Component (Mode B exclusive)

When Live2D is enabled, AIRI does not have the functionality to "switch history conversations/switch characters". atri needs to add a **fold panel component**:

**Functional Requirements**:
- Display both "history conversation list" and "character list" simultaneously
- Adopt a **single fold panel + tabs** design (Option 1)
- Position: top-left corner
- Consistent with AIRI style

**Interaction Design**:
```
┌──────────────────┐
│ [Fold Button ▼]   │
├──────────────────┤
│ [Chats] | [Chars] │  ← Tab switching
├──────────────────┤
│ ● Today's chat    │
│ ● Yesterday's chat│  ← History conversation list
│ ● ...             │
└──────────────────┘
```

**Implementation**: The agent needs to design and implement this on its own, with a style consistent with AIRI.

#### Difference 3: Centralized Architecture

| Comparison Item | AIRI (Decentralized) | atri (Centralized) |
|----------------|---------------------|-------------------|
| API Key Storage | Frontend LocalStorage | Backend YAML configuration |
| Provider Management | Frontend full control | Backend configuration, frontend read-only selection |
| Authentication System | None | GitHub OAuth + whitelist |
| Data Storage | Frontend LocalStorage | Backend API + database |

#### Difference 4: Background Settings Route

AIRI's `/settings/scene` route is pending development; atri uses this route to implement chat background settings:
- Background image local upload (FileReader API -> base64 -> LocalStorage)
- Opacity adjustment (0-100 slider)
- Blur adjustment (0-10 slider)
- Preset backgrounds (solid color/gradient)

---

## 2. Technology Stack

### 2.1 Core Technology Stack

| Category | Technology | Version | Description |
|----------|-----------|---------|-------------|
| **Framework** | Vue 3 | ^3.5.32 | Composition API |
| **Language** | TypeScript | ~6.0.2 | Type safety |
| **Build Tool** | Vite | ^8.0.9 | Fast development, HMR |
| **State Management** | Pinia | ^2.3.1 | Vue 3 officially recommended |
| **Styling** | UnoCSS | ^66.6.8 | Atomic CSS |
| **Component Library** | reka-ui | - | Headless component library |
| **HTTP Client** | axios | ^1.15.1 | API calls |
| **Router** | vue-router | ^4.6.4 | SPA routing |
| **WebSocket** | Native WebSocket API | - | Real-time communication |
| **Local Storage** | localforage | ^1.10.0 | IndexedDB wrapper |
| **Utility Library** | @vueuse/core | ^10.11.1 | Vue composable utilities |
| **Live2D** | pixi-live2d-display | - | Live2D model rendering |

### 2.2 Technology Selection Rationale

#### 2.2.1 Vue 3 + TypeScript

- **Selection reason**: Consistent with AIRI technology stack, facilitating component reuse
- **Composition API**: Better logic reuse (composables)
- **TypeScript**: Type safety, reducing runtime errors

#### 2.2.2 Pinia

- **Selection reason**: Vue 3 officially recommended state management solution
- **Advantages**: Native TypeScript support, DevTools integration, modular design
- **Store division**: chat, chats, characters, user, websocket, settings

#### 2.2.3 UnoCSS

- **Selection reason**: Consistent with AIRI, atomic CSS
- **Advantages**: On-demand generation, zero runtime, responsive prefixes (sm:/md:/lg:)
- **Reuse strategy**: Directly copy AIRI's `uno.config.ts` and theme configuration

#### 2.2.4 reka-ui

- **Selection reason**: Headless component library providing unstyled interactive components
- **Advantages**: Accessibility (a11y), keyboard navigation, works well with UnoCSS
- **Use cases**: Dialog, Dropdown, Tabs, Switch and other interactive components

#### 2.2.5 localforage

- **Selection reason**: Simple wrapper for IndexedDB, API similar to localStorage
- **Advantages**: Supports large data storage, async operations, automatic fallback
- **Use cases**: Background image caching, user preferences, Live2D toggle state

### 2.3 UI/CSS Reuse Strategy

**Core principle: Fully reuse AIRI's UI implementation, zero CSS adjustments.**

#### 2.3.1 Component Reuse Sources

| Source | Path | Reuse Content |
|--------|------|---------------|
| **AIRI Base Components** | `airi/packages/ui/` | Button, Input, Modal, Dropdown, etc. |
| **AIRI Business Components** | `airi/packages/stage-ui/` | Chat components, settings page components |
| **AIRI Main Page** | `airi/packages/stage-web/` | Main page layout (Mode B) |
| **AIRI Settings Pages** | `airi/packages/stage-pages/` | Settings page layout and logic |
| **AIRI Live2D** | `airi/packages/stage-ui-live2d/` | Live2D rendering and expression control |

#### 2.3.2 Style Reuse

- **UnoCSS configuration**: Directly copy `airi/uno.config.ts`
- **Theme variables**: Copy color, font, spacing and other theme configurations
- **Global styles**: Copy global CSS files

#### 2.3.3 Styles Requiring Agent Implementation

The following parts cannot be directly reused from AIRI and need the agent to use the `/frontend-design` skill to implement in AIRI style:

1. **Mode A (ChatGPT style) chat interface**: Sidebar + chat area layout
2. **Fold panel component**: History conversation/character switching panel in Live2D mode
3. **Background settings page**: Image upload + opacity/blur sliders

---

## 3. Architecture Design

### 3.1 Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        View Layer (Pages)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  index.vue   │  │ settings/*   │  │  login.vue   │      │
│  │  (Main Page) │  │(Settings Pages)│ │  (Login Page)│      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Component Layer (Components)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  chat/   │  │ sidebar/ │  │ live2d/  │  │settings/ │   │
│  │ ChatArea │  │ Sidebar  │  │Live2DView│  │SettingsX │   │
│  │ InputBox │  │ CharSel  │  │FoldPanel │  │          │   │
│  │ MsgList  │  │ ChatHist │  │          │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      State Layer (Stores)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │chatStore │  │chatsStore│  │charStore │  │userStore │   │
│  │(Current  │  │(Chat List)│ │(Character│  │(User Auth)│   │
│  │ Chat)    │  │          │  │ Mgmt)    │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ┌──────────┐  ┌──────────┐                                │
│  │ wsStore  │  │settStore │                                │
│  │(WebSocket)│  │(Settings │                                │
│  │          │  │Prefs)    │                                │
│  └──────────┘  └──────────┘                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer (Services)                  │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  composables/     │  │  api/             │                │
│  │  useChat.ts       │  │  client.ts        │                │
│  │  useWebSocket.ts  │  │  characters.ts    │                │
│  │  useLive2D.ts     │  │  chats.ts         │                │
│  │  useBackground.ts │  │  tts.ts / asr.ts  │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Transport Layer (Transport)                │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  HTTP (axios)     │  │  WebSocket        │                │
│  │  REST API Calls   │  │  Real-time Stream │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   atri Backend (FastAPI)                      │
│  REST API + WebSocket + Static File Service                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Directory Structure

```
atri-webui/
├── public/                      # Static assets
│   └── favicon.ico
├── src/
│   ├── main.ts                  # Application entry point
│   ├── App.vue                  # Root component
│   ├── router/
│   │   └── index.ts             # Route configuration
│   ├── pages/                   # Page components
│   │   ├── index.vue            # Main page (dual-mode)
│   │   ├── login.vue            # Login page
│   │   └── settings/            # Settings pages
│   │       ├── index.vue        # Settings home
│   │       ├── account.vue
│   │       ├── airi-card.vue
│   │       ├── consciousness.vue
│   │       ├── speech.vue
│   │       ├── hearing.vue
│   │       ├── vision.vue
│   │       ├── scene.vue
│   │       ├── models.vue
│   │       ├── providers.vue
│   │       ├── data.vue
│   │       ├── connection.vue
│   │       └── system.vue
│   ├── components/              # Shared components
│   │   ├── ui/                  # Copied from AIRI @proj-airi/ui
│   │   │   ├── Button.vue
│   │   │   ├── Input.vue
│   │   │   ├── Modal.vue
│   │   │   └── ...
│   │   ├── chat/                # Chat components
│   │   │   ├── ChatArea.vue
│   │   │   ├── InputBox.vue
│   │   │   ├── MessageItem.vue
│   │   │   └── MessageList.vue
│   │   ├── sidebar/             # Sidebar components (Mode A)
│   │   │   ├── Sidebar.vue
│   │   │   ├── CharacterSelector.vue
│   │   │   └── ChatHistory.vue
│   │   ├── live2d/              # Live2D components (Mode B)
│   │   │   ├── Live2DCanvas.vue
│   │   │   ├── Live2DController.vue
│   │   │   └── FoldPanel.vue    # Fold panel (history + characters)
│   │   └── layouts/             # Layout components
│   │       ├── ChatGPTLayout.vue   # Mode A layout
│   │       └── AIRILayout.vue      # Mode B layout
│   ├── stores/                  # Pinia state management
│   │   ├── chat.ts              # Current chat state
│   │   ├── chats.ts             # Chat list
│   │   ├── characters.ts        # Character management
│   │   ├── user.ts              # User authentication
│   │   ├── websocket.ts         # WebSocket connection
│   │   └── settings.ts          # Settings preferences (including Live2D toggle)
│   ├── composables/             # Composable functions
│   │   ├── useChat.ts           # Chat logic
│   │   ├── useWebSocket.ts      # WebSocket management
│   │   ├── useLive2D.ts         # Live2D control
│   │   └── useBackground.ts     # Background management
│   ├── api/                     # API wrappers
│   │   ├── client.ts            # axios instance
│   │   ├── types.ts             # API type definitions
│   │   ├── characters.ts        # Character API
│   │   ├── chats.ts             # Chat API
│   │   ├── tts.ts               # TTS API
│   │   ├── asr.ts               # ASR API
│   │   ├── live2d.ts            # Live2D API
│   │   ├── auth.ts              # Authentication API
│   │   └── data.ts              # Data management API
│   ├── types/                   # TypeScript types
│   │   ├── chat.ts
│   │   ├── character.ts
│   │   ├── websocket.ts
│   │   └── settings.ts
│   ├── utils/                   # Utility functions
│   │   ├── websocket.ts         # WebSocketManager
│   │   └── storage.ts           # LocalStorage wrapper
│   ├── styles/                  # Global styles (reused from AIRI)
│   │   ├── theme.css
│   │   └── global.css
│   └── assets/                  # Static assets
├── package.json
├── vite.config.ts
├── tsconfig.json
├── uno.config.ts                # UnoCSS configuration (reused from AIRI)
└── 执行准则.md                   # Frontend development execution guidelines
```

### 3.3 Data Flow Design

#### 3.3.1 Chat Data Flow (Unidirectional)

```
User inputs text
    ↓
InputBox.vue → emit('send', text)
    ↓
ChatArea.vue → useChatStore().sendMessage(text)
    ↓
chatStore → Add user message to messages[]
    ↓
wsStore → WebSocket sends { type: "input:text", data: { text, chat_id, character_id } }
    ↓
Backend ChatAgent processes
    ↓
WebSocket receives { type: "output:chat:chunk", data: { chunk, chat_id } }
    ↓
chatStore → Append chunk to streamingText
    ↓
WebSocket receives { type: "output:chat:complete", data: { full_reply, chat_id } }
    ↓
chatStore → Convert streamingText to complete message, add to messages[]
    ↓
MessageList.vue → Reactive update display
```

#### 3.3.2 Data Storage Strategy

| Data Type | Storage Location | Management Method | Description |
|-----------|-----------------|-------------------|-------------|
| Chat History | Backend API | Read-only display | `GET /api/chats` |
| Character Cards | Backend API | Full CRUD | `GET/POST /api/characters` |
| LLM Provider | Backend YAML | Read-only list | Frontend cannot modify |
| TTS/ASR Provider | Backend YAML | Read-only selection | Frontend can switch, cannot add new ones |
| Background Settings | Frontend LocalStorage | Full control | base64 image + opacity |
| UI Preferences | Frontend LocalStorage | Full control | Language, theme, font |
| Live2D Toggle | Frontend LocalStorage | Full control | boolean |
| User Authentication | Frontend Cookie/Storage | JWT Token | Issued by backend |

### 3.4 Route Design

#### 3.4.1 Route Table

```typescript
// src/router/index.ts

const routes = [
  // Main page (dual-mode)
  {
    path: '/',
    name: 'home',
    component: () => import('@/pages/index.vue')
  },
  
  // Login page
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/login.vue')
  },
  
  // Settings pages
  {
    path: '/settings',
    component: () => import('@/pages/settings/index.vue'),
    children: [
      { path: 'account', component: () => import('@/pages/settings/account.vue') },
      { path: 'airi-card', component: () => import('@/pages/settings/airi-card.vue') },
      { path: 'modules/consciousness', component: () => import('@/pages/settings/consciousness.vue') },
      { path: 'modules/speech', component: () => import('@/pages/settings/speech.vue') },
      { path: 'modules/hearing', component: () => import('@/pages/settings/hearing.vue') },
      { path: 'modules/vision', component: () => import('@/pages/settings/vision.vue') },
      { path: 'scene', component: () => import('@/pages/settings/scene.vue') },
      { path: 'models', component: () => import('@/pages/settings/models.vue') },
      { path: 'providers', component: () => import('@/pages/settings/providers.vue') },
      { path: 'data', component: () => import('@/pages/settings/data.vue') },
      { path: 'connection', component: () => import('@/pages/settings/connection.vue') },
      { path: 'system', component: () => import('@/pages/settings/system.vue') },
    ]
  }
]
```

#### 3.4.2 Route Guards (Authentication Interception)

```typescript
// src/router/index.ts

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore();
  
  // Whitelisted routes (no authentication required)
  const publicRoutes = ['/login', '/auth/callback'];
  
  if (publicRoutes.includes(to.path)) {
    next();
    return;
  }
  
  // Check authentication status
  if (!userStore.isAuthenticated) {
    next('/login');
    return;
  }
  
  next();
});
```

#### 3.4.3 Main Page Dual-mode Switching Logic

```vue
<!-- src/pages/index.vue -->
<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';
import ChatGPTLayout from '@/components/layouts/ChatGPTLayout.vue';
import AIRILayout from '@/components/layouts/AIRILayout.vue';

const settingsStore = useSettingsStore();
const live2dEnabled = computed(() => settingsStore.live2dEnabled);
</script>

<template>
  <!-- Mode A: ChatGPT Style (Live2D disabled) -->
  <ChatGPTLayout v-if="!live2dEnabled" />
  
  <!-- Mode B: AIRI Style (Live2D enabled) -->
  <AIRILayout v-else />
</template>
```

**Switching Flow**:
1. User toggles the Live2D switch on the `/settings/models` page
2. `settingsStore.live2dEnabled` updates, synchronously written to LocalStorage
3. User returns to the main page `/`
4. `index.vue`'s `onMounted` reads the latest state
5. Conditionally renders the corresponding layout component

**Reference Code Paths**:
- AIRI main page: `airi/apps/stage-web/src/pages/index.vue`
- AIRI settings pages: `airi/packages/stage-pages/src/`
- atri current implementation: `atri-webui/src/pages/index.vue`

## 4. Core Component Design

### 4.1 Component List

| Component | Responsibility | Dependent Store | Priority | Phase | Mode |
|-----------|---------------|-----------------|----------|-------|------|
| **ChatArea** | Chat area container | chat, websocket | P0 | Phase 6 | Mode A |
| **MessageList** | Message list rendering | - | P0 | Phase 6 | Mode A |
| **MessageItem** | Single message display | - | P0 | Phase 6 | Mode A |
| **InputBox** | Message input box | - | P0 | Phase 6 | Mode A |
| **Sidebar** | Sidebar container | - | P0 | Phase 6 | Mode A |
| **CharacterSelector** | Character selector | characters | P0 | Phase 6 | Mode A |
| **ChatHistory** | Chat history list | chats | P0 | Phase 6 | Mode A |
| **Live2DCanvas** | Live2D rendering | - | P2 | Phase 8 | Mode B |
| **FoldPanel** | Fold panel | chats, characters | P2 | Phase 8 | Mode B |
| **ChatGPTLayout** | ChatGPT style layout | - | P0 | Phase 6 | Mode A |
| **AIRILayout** | AIRI style layout | - | P2 | Phase 8 | Mode B |

**Notes**:
- **Mode A**: ChatGPT style when Live2D is disabled
- **Mode B**: AIRI style when Live2D is enabled
- **Priority**: P0 = core feature, P1 = enhancement, P2 = advanced feature

---

### 4.2 Mode A Components (ChatGPT Style)

#### 4.2.1 ChatArea (Chat Area Container)

**Responsibilities**:
- Coordinate the interaction between MessageList and InputBox
- Handle message sending events
- Manage chat area layout

**Interface Definition**:
```typescript
// Props: none
// Events: none
// Dependent Stores: chatStore, wsStore

interface ChatAreaMethods {
  handleSendMessage(text: string): Promise<void>
}
```

**Implementation Notes**:
```typescript
// Core logic (pseudocode)
const handleSendMessage = async (text: string) => {
  // 1. Validate input
  if (!text.trim() || isStreaming) return
  
  // 2. Add user message locally
  chatStore.addUserMessage(text)
  
  // 3. Send via WebSocket
  await wsStore.sendMessage({
    type: 'input:text',
    data: { text, chat_id, character_id }
  })
}
```

**Key Considerations**:
- ⚠️ Check WebSocket connection status before sending
- ⚠️ Disable send button during streaming input
- ⚠️ Notify user when message sending fails

---

#### 4.2.2 MessageList (Message List)

**Responsibilities**:
- Render message list
- Auto-scroll to latest message
- Support virtual scrolling (long list optimization)

**Interface Definition**:
```typescript
interface MessageListProps {
  messages: Message[]
  isStreaming?: boolean
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  type: 'text' | 'error'
}
```

**Implementation Notes**:
```typescript
// Auto-scroll logic (pseudocode)
watch(() => messages.length, async () => {
  await nextTick()
  scrollToBottom()
})

const scrollToBottom = () => {
  listRef.scrollTop = listRef.scrollHeight
}
```

**Key Considerations**:
- ⚠️ Use `nextTick` to ensure DOM updates before scrolling
- ⚠️ Consider virtual scrolling optimization for long lists (>100 items)
- ⚠️ Continuously scroll to bottom during streaming input

---

#### 4.2.3 MessageItem (Single Message)

**Responsibilities**:
- Render a single message (user/AI)
- Distinguish message types (text/error)
- Support Markdown rendering (optional)

**Interface Definition**:
```typescript
interface MessageItemProps {
  message: Message
}
```

**Design Notes**:
- User message: right-aligned, blue bubble
- AI message: left-aligned, gray bubble
- Error message: red border, warning icon

**Key Considerations**:
- ⚠️ Long text needs automatic word wrapping (`word-break: break-word`)
- ⚠️ Timestamp formatting (show time for today, show date for yesterday)

---

#### 4.2.4 InputBox (Message Input Box)

**Responsibilities**:
- Receive user input
- Support multi-line input (auto-expand)
- Support keyboard shortcuts (Enter to send, Shift+Enter for new line)

**Interface Definition**:
```typescript
interface InputBoxProps {
  disabled?: boolean
  maxLength?: number
}

interface InputBoxEmits {
  (e: 'send', text: string): void
}
```

**Implementation Notes**:
```typescript
// Keyboard shortcut handling (pseudocode)
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send', inputText)
    inputText = ''
  }
}

// Auto-adjust height
const handleInput = () => {
  textarea.style.height = 'auto'
  textarea.style.height = textarea.scrollHeight + 'px'
}
```

**Key Considerations**:
- ⚠️ Maximum height limit (avoid filling the screen)
- ⚠️ Character count and limit (default 2000 characters)
- ⚠️ Show "Connecting..." prompt when disabled

---

#### 4.2.5 Sidebar (Sidebar Container)

**Responsibilities**:
- Provide tab switching (chat history / character selection)
- Manage sidebar layout

**Interface Definition**:
```typescript
type TabType = 'history' | 'character'
```

**Design Notes**:
- Fixed width: 256px (`w-64`)
- Tab switching animation
- Responsive: collapsible on mobile

---

#### 4.2.6 CharacterSelector (Character Selector)

**Responsibilities**:
- Display available character list
- Switch the current chat character

**Interface Definition**:
```typescript
// Dependent Stores: charactersStore, chatStore
```

**Implementation Notes**:
```typescript
// Switch character (pseudocode)
const handleSelectCharacter = (characterId: string) => {
  chatStore.setCurrentCharacter(characterId)
  // Optional: automatically create a new conversation
}
```

**Key Considerations**:
- ⚠️ Highlight the current character
- ⚠️ Show empty state prompt "Go to settings page to create a character"

---

#### 4.2.7 ChatHistory (Chat History List)

**Responsibilities**:
- Display history conversation list
- Switch conversations, create new conversations, delete conversations

**Interface Definition**:
```typescript
// Dependent Stores: chatsStore, chatStore
```

**Implementation Notes**:
```typescript
// Delete conversation (pseudocode)
const handleDeleteChat = async (chatId: string, event: Event) => {
  event.stopPropagation() // Prevent bubbling
  if (confirm('Are you sure you want to delete this conversation?')) {
    await chatsStore.deleteChat(chatId)
  }
}
```

**Key Considerations**:
- ⚠️ Delete button appears on hover
- ⚠️ Automatically switch to the first conversation after deleting the current one
- ⚠️ Date formatting (today/yesterday/date)

---

### 4.3 Mode B Components (AIRI Style)

#### 4.3.1 Live2DCanvas (Live2D Rendering)

**Responsibilities**:
- Render Live2D model using PixiJS
- Handle model interaction (drag, zoom)

**Dependency Installation**:
```json
{
  "dependencies": {
    "pixi.js": "^7.x",
    "pixi-live2d-display": "^0.5.x",
    "jszip": "^3.x"
  }
}
```

**Implementation Notes**:
```typescript
// Load model (pseudocode)
const loadModel = async () => {
  const app = new Application({ view: canvas, backgroundAlpha: 0 })
  const model = await Live2DModel.from(modelUrl)
  app.stage.addChild(model)
  
  // Set position and scale
  model.x = window.innerWidth / 2
  model.y = window.innerHeight / 2
  model.scale.set(0.5)
}
```

**Integration Notes**:
- See "Live-2d Design Document.md" Chapter 4: Frontend Integration Plan
- Expression control: Chapter 5 (5 LLM tool interfaces)
- Auto animation: Chapter 6 (blinking, breathing, mouse tracking)

**Backend API Integration**:
```typescript
GET /api/live2d/models          // Get model list
POST /api/live2d/set-model      // Switch model
POST /api/live2d/models         // Upload model (Phase 8)
DELETE /api/live2d/models/{id}  // Delete model (Phase 8)
```

**Key Considerations**:
- ⚠️ Model files are large (15MB), show loading progress on first load
- ⚠️ Browser caches model files
- ⚠️ Destroy PixiJS application when component unmounts

---

#### 4.3.2 FoldPanel (Fold Panel)

**Responsibilities**:
- Provide history conversation and character switching functionality
- Fold/unfold animation
- Consistent with AIRI style

**Design Plan**: Single fold panel + tabs (Option 1)

**Interface Definition**:
```typescript
// Dependent Stores: chatsStore, charactersStore, chatStore
```

**Implementation Notes**:
```typescript
// Toggle panel (pseudocode)
const togglePanel = () => {
  isExpanded = !isExpanded
}

// Auto-close after selection
const handleSelectChat = (chatId: string) => {
  chatStore.loadChat(chatId)
  isExpanded = false
}
```

**Design Notes**:
- Position: fixed in top-left corner
- Semi-transparent background (`bg-white/95`) + frosted glass effect (`backdrop-blur-md`)
- Slide-fade animation (`slide-fade`)
- Gradient button (`from-purple-500 to-pink-500`)

**Key Considerations**:
- ⚠️ Auto-close when clicking outside area (optional)
- ⚠️ Mobile adaptation (full screen display)

---

### 4.4 Layout Components

#### 4.4.1 ChatGPTLayout (Mode A Layout)

**Responsibilities**: Compose Sidebar and ChatArea

**Structure**:
```
┌─────────────────────────────────────┐
│  Sidebar  │  ChatArea               │
│  (256px)  │  (flex-1)               │
└─────────────────────────────────────┘
```

**Implementation Notes**:
```vue
<template>
  <div class="flex h-screen">
    <Sidebar class="flex-shrink-0" />
    <ChatArea class="flex-1" />
  </div>
</template>
```

---

#### 4.4.2 AIRILayout (Mode B Layout)

**Responsibilities**: Compose Live2DCanvas, FoldPanel, ChatBox

**Structure**:
```
┌─────────────────────────────────────┐
│  [FoldPanel]     Live2D Model       │
│                                     │
│              ┌──────────────┐       │
│              │  ChatBox     │       │
│              └──────────────┘       │
└─────────────────────────────────────┘
```

**Implementation Notes**:
```vue
<template>
  <div class="relative h-screen">
    <Live2DCanvas />
    <FoldPanel />
    <div class="fixed bottom-4 right-4 w-96">
      <ChatBox />
    </div>
  </div>
</template>
```

**Reference Implementation**:
- Fully reuse AIRI: `airi/apps/stage-web/src/pages/index.vue`

---

### 4.5 Shared Components (Reused from AIRI)

**Design Principle**: Reuse base UI components from AIRI, do not redevelop

| Component | AIRI Path | Purpose |
|-----------|----------|---------|
| Button | `airi/packages/ui/` | Button component |
| Input | `airi/packages/ui/` | Input component |
| Modal | `airi/packages/ui/` | Modal dialog component |
| Dropdown | `airi/packages/ui/` | Dropdown menu |
| Switch | `airi/packages/ui/` | Switch component |
| Slider | `airi/packages/ui/` | Slider component |
| Tabs | `airi/packages/ui/` | Tab component |
| Toast | `airi/packages/ui/` | Toast notification |

**Usage**:
1. Directly copy to `atri-webui/src/components/ui/`
2. Or reference via pnpm workspace (if using monorepo)

**Style Reuse**:
- Copy `airi/uno.config.ts` -> `atri-webui/uno.config.ts`
- Copy theme variables and global styles

---

### 4.6 Component Dependency Diagram

```
Main Page (index.vue)
├── Mode A: ChatGPTLayout
│   ├── Sidebar
│   │   ├── CharacterSelector → charactersStore
│   │   └── ChatHistory → chatsStore
│   └── ChatArea → chatStore, wsStore
│       ├── MessageList
│       │   └── MessageItem
│       └── InputBox
│
└── Mode B: AIRILayout
    ├── Live2DCanvas
    ├── FoldPanel → chatsStore, charactersStore
    └── ChatBox (simplified ChatArea)
```

---

**Chapter 4 Complete!**

Next step: Write concise version of Chapter 5 (State Management Design)

---

## 5. State Management Design

### 5.1 Store List

| Store | Responsibility | Dependent Store | Priority | Phase |
|-------|---------------|-----------------|----------|-------|
| **chat** | Current chat state | websocket | P0 | Phase 6 |
| **chats** | Chat list management | user | P0 | Phase 6 |
| **characters** | Character management | user | P0 | Phase 6 (read-only) / Phase 7 (CRUD) |
| **user** | User authentication | - | P1 | Phase 7 |
| **websocket** | WebSocket connection | user | P0 | Phase 6 |
| **settings** | Settings preferences | - | P0 | Phase 6 |
| **modules** | Module configuration | user | P2 | Phase 10 |

**Notes**:
- **P0**: Core feature, must be implemented in Phase 6
- **P1**: Enhancement, implemented in Phase 7
- **P2**: Advanced feature, implemented in Phase 10

---

### 5.2 Store Dependency Diagram

```
user (P1, Phase 7)
  ↓
websocket (P0, Phase 6) ← chat (P0, Phase 6)
  ↓                          ↓
settings (P0, Phase 6)   chats (P0, Phase 6)
                             ↓
                         characters (P0/P1, Phase 6/7)
```

**Dependency Notes**:
- `user` is the foundation, providing authentication token
- `websocket` depends on `user`'s token for connection
- `chat` depends on `websocket` for sending messages
- `chats` and `characters` depend on `user`'s token for API calls

---

### 5.3 Chat Store (Current Chat State)

**Responsibilities**:
- Manage current chat's message list
- Handle streaming input
- Send messages

**Interface Definition**:
```typescript
interface ChatStore {
  // State
  currentChatId: string | null
  messages: Message[]
  streamingText: string
  isStreaming: boolean
  currentCharacterId: string | null
  
  // Getters
  currentMessages: ComputedRef<Message[]>
  currentCharacter: ComputedRef<Character | null>
  
  // Actions
  loadChat(chatId: string): Promise<void>
  sendMessage(text: string): Promise<void>
  addUserMessage(text: string): void
  startStreaming(): void
  appendStreamingText(chunk: string): void
  finishStreaming(): void
  handleWebSocketMessage(message: any): void
}
```

**Implementation Notes**:
```typescript
// Send message (pseudocode)
const sendMessage = async (text: string) => {
  // 1. Add user message locally
  addUserMessage(text)
  
  // 2. Start streaming
  startStreaming()
  
  // 3. Send via WebSocket
  await wsStore.sendMessage({
    type: 'input:text',
    data: { text, chat_id, character_id }
  })
}

// Handle WebSocket message (pseudocode)
const handleWebSocketMessage = (message: any) => {
  switch (message.type) {
    case 'output:chat:chunk':
      appendStreamingText(message.data.chunk)
      break
    case 'output:chat:complete':
      finishStreaming()
      break
    case 'error':
      finishStreaming()
      addErrorMessage(message.data.message)
      break
  }
}
```

**Key Considerations**:
- ⚠️ Disable send button during streaming input
- ⚠️ Message ID generated using timestamp (`msg_${Date.now()}`)
- ⚠️ Clear streaming state when switching conversations

---

### 5.4 Chats Store (Chat List)

**Responsibilities**:
- Manage history conversation list
- Create/delete conversations

**Interface Definition**:
```typescript
interface ChatsStore {
  // State
  chatList: Chat[]
  isLoading: boolean
  
  // Actions
  loadChats(): Promise<void>
  createNewChat(): Promise<Chat>
  deleteChat(chatId: string): Promise<void>
  updateChatTitle(chatId: string, title: string): Promise<void>
}

interface Chat {
  id: string
  title: string
  character_id: string | null
  created_at: number
  updated_at: number
}
```

**Implementation Notes**:
```typescript
// Delete conversation (pseudocode)
const deleteChat = async (chatId: string) => {
  await fetch(`/api/chats/${chatId}`, { method: 'DELETE' })
  
  // Remove from list
  chatList = chatList.filter(c => c.id !== chatId)
  
  // If deleted the current conversation, switch to the first one
  if (chatStore.currentChatId === chatId) {
    if (chatList.length > 0) {
      await chatStore.loadChat(chatList[0].id)
    } else {
      chatStore.clearMessages()
    }
  }
}
```

**Key Considerations**:
- ⚠️ Automatically switch to the new conversation after creating one
- ⚠️ Conversation list sorted by update time in descending order

---

### 5.5 Characters Store (Character Management)

**Responsibilities**:
- Manage character list
- Create/edit/delete characters (Phase 7)

**Interface Definition**:
```typescript
interface CharactersStore {
  // State
  characters: Character[]
  isLoading: boolean
  
  // Actions
  loadCharacters(): Promise<void>
  createCharacter(character: Omit<Character, 'id'>): Promise<Character>  // Phase 7
  updateCharacter(id: string, updates: Partial<Character>): Promise<Character>  // Phase 7
  deleteCharacter(id: string): Promise<void>  // Phase 7
}

interface Character {
  id: string
  name: string
  description: string
  avatar?: string
  persona: string
  created_at: number
}
```

**Phase Division**:
- **Phase 6**: Only implement `loadCharacters()` (read-only)
- **Phase 7**: Implement full CRUD

**Key Considerations**:
- ⚠️ Phase 6 read-only mode, character list loaded from backend
- ⚠️ After Phase 7 implements CRUD, backend API support is needed

---

### 5.6 User Store (User Authentication)

**Responsibilities**:
- Manage user login state
- GitHub OAuth authentication
- Token management

**Interface Definition**:
```typescript
interface UserStore {
  // State
  user: User | null
  token: string | null
  isLoading: boolean
  
  // Getters
  isAuthenticated: ComputedRef<boolean>
  
  // Actions
  init(): Promise<void>
  loginWithGitHub(): void
  handleOAuthCallback(code: string): Promise<void>
  refreshToken(): Promise<void>
  logout(): void
}
```

**Implementation Notes**:
```typescript
// GitHub OAuth login (pseudocode)
const loginWithGitHub = () => {
  const authUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&scope=read:user`
  window.location.href = authUrl
}

// Handle OAuth callback (pseudocode)
const handleOAuthCallback = async (code: string) => {
  const response = await fetch('/api/auth/github/callback', {
    method: 'POST',
    body: JSON.stringify({ code })
  })
  const { token, user } = await response.json()
  
  // Save token
  localStorage.setItem('auth_token', token)
  this.token = token
  this.user = user
}
```

**Key Considerations**:
- ⚠️ Token stored in localStorage
- ⚠️ Auto-refresh token when expired or redirect to login page
- ⚠️ Clear all local data on logout

---

### 5.7 WebSocket Store (Connection State)

**Responsibilities**:
- Manage WebSocket connection
- Exponential backoff reconnection
- Heartbeat mechanism
- Message queue

**Interface Definition**:
```typescript
interface WebSocketStore {
  // State
  ws: WebSocket | null
  connected: boolean
  reconnectAttempts: number
  messageQueue: any[]
  
  // Getters
  connectionStatus: ComputedRef<'connected' | 'reconnecting' | 'disconnected'>
  
  // Actions
  connect(): Promise<void>
  disconnect(): void
  sendMessage(message: any): Promise<void>
}
```

**Implementation Notes**:
```typescript
// Exponential backoff reconnection (pseudocode)
const handleReconnect = () => {
  if (reconnectAttempts >= maxReconnectAttempts) {
    console.error('Maximum reconnection attempts reached')
    return
  }
  
  reconnectAttempts++
  
  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
  const delay = Math.min(
    1000 * Math.pow(2, reconnectAttempts - 1),
    30000
  )
  
  setTimeout(() => connect(), delay)
}

// Heartbeat mechanism (pseudocode)
const startHeartbeat = () => {
  heartbeatInterval = setInterval(() => {
    if (connected) {
      sendMessage({ type: 'ping' })
    }
  }, 30000) // 30-second heartbeat
}

// Message queue (pseudocode)
const sendMessage = async (message: any) => {
  if (!connected) {
    // Connection lost, add to queue
    messageQueue.push(message)
    return
  }
  
  ws.send(JSON.stringify(message))
}
```

**Key Considerations**:
- ⚠️ Reconnection strategy: exponential backoff, max 5 attempts, max delay 30 seconds
- ⚠️ Heartbeat interval: 30 seconds
- ⚠️ Offline message queue: auto-send when connection is restored
- ⚠️ Check if user.token exists before connecting

---

### 5.8 Settings Store (Settings Preferences)

**Responsibilities**:
- Manage UI preferences
- Live2D toggle
- Theme, language, background

**Interface Definition**:
```typescript
interface SettingsStore {
  // State
  live2dEnabled: boolean
  theme: 'light' | 'dark' | 'auto'
  language: 'zh-CN' | 'en-US'
  fontSize: 'small' | 'medium' | 'large'
  background: {
    type: 'image' | 'color' | 'gradient'
    value: string  // base64 image or color value
    opacity: number
    blur: number
  }
  
  // Actions
  init(): void
  toggleLive2D(enabled: boolean): Promise<void>
  setTheme(theme: string): void
  setLanguage(language: string): void
  setBackground(bg: Background): void
  uploadBackgroundImage(file: File): Promise<string>
}
```

**Implementation Notes**:
```typescript
// Live2D toggle switch (pseudocode)
const toggleLive2D = async (enabled: boolean) => {
  live2dEnabled = enabled
  localStorage.setItem('live2d_enabled', String(enabled))
  
  // Trigger main page re-mount (via route navigation)
  if (router.currentRoute.path === '/') {
    await router.push('/temp')
    await router.push('/')
  }
}

// Apply theme (pseudocode)
const applyTheme = () => {
  let actualTheme = theme
  
  // auto mode: based on system preference
  if (actualTheme === 'auto') {
    actualTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  
  document.documentElement.classList.remove('light', 'dark')
  document.documentElement.classList.add(actualTheme)
}
```

**Key Considerations**:
- ⚠️ All settings persisted to localStorage
- ⚠️ Live2D toggle requires re-mounting the main page component
- ⚠️ Background image converted to base64 for storage (note size limit)

---

### 5.9 Store Initialization Flow

**Initialization Order**:
```typescript
// src/main.ts
const initStores = async () => {
  // 1. Initialize settings (restore from localStorage)
  const settingsStore = useSettingsStore()
  settingsStore.init()
  settingsStore.applyTheme()
  
  // 2. Initialize user authentication
  const userStore = useUserStore()
  await userStore.init()
  
  // 3. If logged in, initialize WebSocket
  if (userStore.isAuthenticated) {
    const wsStore = useWebSocketStore()
    await wsStore.connect()
    
    // 4. Load chat list and character list
    const chatsStore = useChatsStore()
    const charactersStore = useCharactersStore()
    await Promise.all([
      chatsStore.loadChats(),
      charactersStore.loadCharacters()
    ])
  }
}

// Start application
initStores().then(() => {
  app.mount('#app')
})
```

**Key Considerations**:
- ⚠️ Must initialize in order (user -> websocket -> others)
- ⚠️ Skip WebSocket connection when not logged in
- ⚠️ Show error message when initialization fails

---

### 5.10 Store Usage Example

**Using Store in Component**:
```vue
<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import { useWebSocketStore } from '@/stores/websocket'

const chatStore = useChatStore()
const wsStore = useWebSocketStore()

// Use computed to get reactive data
const messages = computed(() => chatStore.currentMessages)
const connected = computed(() => wsStore.connected)

// Call actions
const handleSend = async (text: string) => {
  await chatStore.sendMessage(text)
}
</script>
```

---

**Chapter 5 Complete!**

Next step: Replace Chapters 4-5 in the main document with the concise version

---

**Chapters 4-5 have been rewritten as concise versions!**

---

## 6. WebSocket Communication Design

### 6.1 Communication Protocol

#### 6.1.1 Message Format

**Client Sends**:
```typescript
interface ClientMessage {
  type: 'input:text' | 'ping'
  data?: {
    text?: string
    chat_id?: string
    character_id?: string
  }
}
```

**Server Response**:
```typescript
interface ServerMessage {
  type: 'output:chat:chunk' | 'output:chat:complete' | 'error' | 'pong'
  data?: {
    chunk?: string
    full_reply?: string
    chat_id?: string
    message?: string
  }
}
```

#### 6.1.2 Event Types

| Event Type | Direction | Description | Data |
|-----------|-----------|-------------|------|
| `input:text` | Client -> Server | Send user message | `{ text, chat_id, character_id }` |
| `output:chat:chunk` | Server -> Client | Streaming output fragment | `{ chunk, chat_id }` |
| `output:chat:complete` | Server -> Client | Streaming output complete | `{ full_reply, chat_id }` |
| `error` | Server -> Client | Error message | `{ message }` |
| `ping` | Client -> Server | Heartbeat check | none |
| `pong` | Server -> Client | Heartbeat response | none |

---

### 6.2 Connection Management

#### 6.2.1 Connection Flow

```
1. User logs in -> Obtain token
2. Initialize WebSocket -> ws://localhost:8430/ws?token={token}
3. Connection successful -> Start heartbeat
4. Send queued messages -> Handle offline messages
```

#### 6.2.2 Connection State Machine

```
disconnected → connecting → connected
     ↑              ↓            ↓
     └──────── reconnecting ←────┘
```

**State Descriptions**:
- `disconnected`: Not connected
- `connecting`: Connecting
- `connected`: Connected
- `reconnecting`: Reconnecting

---

### 6.3 Reconnection Strategy

#### 6.3.1 Exponential Backoff Algorithm

**Parameter Configuration**:
```typescript
const reconnectConfig = {
  maxAttempts: 5,           // Maximum reconnection attempts
  initialDelay: 1000,       // Initial delay (1 second)
  maxDelay: 30000,          // Maximum delay (30 seconds)
  backoffFactor: 2          // Backoff factor
}
```

**Delay Calculation**:
```typescript
// Pseudocode
delay = min(initialDelay * pow(backoffFactor, attempts - 1), maxDelay)

// Actual delay sequence:
// 1st attempt: 1 second
// 2nd attempt: 2 seconds
// 3rd attempt: 4 seconds
// 4th attempt: 8 seconds
// 5th attempt: 16 seconds
// 6th+ attempts: 30 seconds (maximum)
```

#### 6.3.2 Reconnection Flow Diagram

```
Connection lost
  ↓
Check reconnection count < maxAttempts?
  ↓ Yes
Calculate delay time
  ↓
Wait for delay
  ↓
Attempt reconnection
  ↓
Success? → Reset reconnection counter
  ↓ No
Reconnection count +1 → Return to check
  ↓ No (reached maximum attempts)
Stop reconnection, show error
```

**Key Considerations**:
- ⚠️ Reset counter after successful reconnection
- ⚠️ Stop reconnection after reaching max attempts, prompt user to manually refresh
- ⚠️ Pause/resume reconnection when page visibility changes

---

### 6.4 Heartbeat Mechanism

#### 6.4.1 Heartbeat Parameters

```typescript
const heartbeatConfig = {
  interval: 30000,          // Heartbeat interval (30 seconds)
  timeout: 5000,            // Heartbeat timeout (5 seconds)
  missedLimit: 3            // Allowed missed count
}
```

#### 6.4.2 Heartbeat Logic

```typescript
// Pseudocode
startHeartbeat() {
  heartbeatInterval = setInterval(() => {
    if (connected) {
      send({ type: 'ping' })
      
      // Set timeout detection
      heartbeatTimeout = setTimeout(() => {
        missedHeartbeats++
        if (missedHeartbeats >= missedLimit) {
          // Heartbeat timeout, actively disconnect and reconnect
          disconnect()
          reconnect()
        }
      }, timeout)
    }
  }, interval)
}

// Reset when pong is received
onPong() {
  clearTimeout(heartbeatTimeout)
  missedHeartbeats = 0
}
```

**Key Considerations**:
- ⚠️ Start heartbeat immediately after connection is established
- ⚠️ Stop heartbeat when connection is lost
- ⚠️ Reset timeout counter when pong is received

---

### 6.5 Message Queue

#### 6.5.1 Queue Design

**Purpose**: Cache messages during disconnection, auto-send when connection is restored

**Implementation Notes**:
```typescript
// Pseudocode
const messageQueue: ClientMessage[] = []

sendMessage(message: ClientMessage) {
  if (!connected) {
    // Connection lost, add to queue
    messageQueue.push(message)
    console.warn('WebSocket not connected, message added to queue')
    return
  }
  
  // Connection normal, send directly
  ws.send(JSON.stringify(message))
}

// Send queued messages after connection is restored
onConnected() {
  while (messageQueue.length > 0) {
    const message = messageQueue.shift()
    ws.send(JSON.stringify(message))
  }
}
```

**Key Considerations**:
- ⚠️ Queue size limit (avoid memory overflow)
- ⚠️ Queue persistence to localStorage (optional)
- ⚠️ Failed messages re-added to queue

---

### 6.6 Error Handling

#### 6.6.1 Error Types

| Error Type | Trigger Condition | Handling Method |
|-----------|-------------------|-----------------|
| **Connection Failure** | Unable to establish connection | Auto-reconnect |
| **Connection Timeout** | Connection establishment timeout | Auto-reconnect |
| **Heartbeat Timeout** | Consecutive missed heartbeats | Actively disconnect and reconnect |
| **Message Send Failure** | send() throws exception | Add to queue, send after reconnection |
| **Message Parse Failure** | JSON.parse() fails | Log error, ignore message |
| **Business Error** | Server returns error | Show error notification |

#### 6.6.2 Error Handling Flow

```typescript
// Pseudocode
ws.onerror = (error) => {
  console.error('WebSocket error:', error)
  // Do not actively disconnect, wait for onclose to trigger reconnection
}

ws.onclose = (event) => {
  connected = false
  stopHeartbeat()
  
  // Determine close reason
  if (event.code === 1000) {
    // Normal close, do not reconnect
    return
  }
  
  // Abnormal close, attempt reconnection
  handleReconnect()
}

ws.onmessage = (event) => {
  try {
    const message = JSON.parse(event.data)
    handleMessage(message)
  } catch (error) {
    console.error('Message parse failed:', error)
    // Ignore invalid messages
  }
}
```

**Key Considerations**:
- ⚠️ Distinguish between normal and abnormal close
- ⚠️ Show user-friendly notifications for business errors
- ⚠️ Log errors for debugging

---

### 6.7 WebSocket URL Configuration

**Development Environment**:
```typescript
// .env.development
VITE_WS_URL=ws://localhost:8430/ws
```

**Production Environment**:
```typescript
// .env.production
VITE_WS_URL=wss://your-domain.com/ws
```

**Dynamic URL Construction**:
```typescript
const wsUrl = `${import.meta.env.VITE_WS_URL}?token=${userStore.token}`
```

**Key Considerations**:
- ⚠️ Use wss (encrypted) in production
- ⚠️ Token passed via query parameter
- ⚠️ Support custom port and path

---

**Chapter 6 Complete!**

## 7. HTTP API Integration

### 7.1 API Client Wrapper

#### 7.1.1 Axios Configuration

**Base Configuration**:
```typescript
// src/api/client.ts
import axios from 'axios'
import { useUserStore } from '@/stores/user'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8430',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor: inject token
apiClient.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: unified error handling
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired, redirect to login
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

**Key Considerations**:
- ⚠️ Request interceptor automatically injects token
- ⚠️ 401 error auto-redirects to login page
- ⚠️ Timeout is 30 seconds (adjustable as needed)

---

### 7.2 API Module Division

| Module | File | Responsibility | Phase |
|--------|------|---------------|-------|
| **Auth API** | `auth.ts` | GitHub OAuth, token management | Phase 7 |
| **Chat API** | `chats.ts` | Chat CRUD | Phase 6 |
| **Character API** | `characters.ts` | Character CRUD | Phase 6/7 |
| **TTS API** | `tts.ts` | TTS Provider management | Phase 10 |
| **ASR API** | `asr.ts` | ASR Provider management | Phase 10 |
| **Live2D API** | `live2d.ts` | Model management | Phase 8 |
| **Data Management API** | `data.ts` | Import/Export | Phase 9 |

---

### 7.3 Authentication API

**Interface Definition**:
```typescript
// src/api/auth.ts
export const authAPI = {
  // GitHub OAuth callback
  githubCallback(code: string): Promise<{ token: string; user: User }> {
    return apiClient.post('/api/auth/github/callback', { code })
  },
  
  // Get current user info
  me(): Promise<{ user: User }> {
    return apiClient.get('/api/auth/me')
  },
  
  // Refresh token
  refresh(): Promise<{ token: string }> {
    return apiClient.post('/api/auth/refresh')
  }
}
```

**API Endpoints**:
```
POST /api/auth/github/callback  # GitHub OAuth callback
GET  /api/auth/me               # Get user info
POST /api/auth/refresh          # Refresh token
```

---

### 7.4 Chat API

**Interface Definition**:
```typescript
// src/api/chats.ts
export const chatsAPI = {
  // Get chat list
  list(): Promise<{ chats: Chat[] }> {
    return apiClient.get('/api/chats')
  },
  
  // Get chat details
  get(chatId: string): Promise<{ chat: Chat; messages: Message[] }> {
    return apiClient.get(`/api/chats/${chatId}`)
  },
  
  // Create new chat
  create(data: { title?: string; character_id?: string }): Promise<{ chat: Chat }> {
    return apiClient.post('/api/chats', data)
  },
  
  // Update chat title
  update(chatId: string, data: { title: string }): Promise<{ chat: Chat }> {
    return apiClient.patch(`/api/chats/${chatId}`, data)
  },
  
  // Delete chat
  delete(chatId: string): Promise<{ success: boolean }> {
    return apiClient.delete(`/api/chats/${chatId}`)
  }
}
```

**API Endpoints**:
```
GET    /api/chats           # Get chat list
GET    /api/chats/{id}      # Get chat details
POST   /api/chats           # Create chat
PATCH  /api/chats/{id}      # Update chat
DELETE /api/chats/{id}      # Delete chat
```

---

### 7.5 Character API

**Interface Definition**:
```typescript
// src/api/characters.ts
export const charactersAPI = {
  // Get character list
  list(): Promise<{ characters: Character[] }> {
    return apiClient.get('/api/characters')
  },
  
  // Get character details
  get(characterId: string): Promise<{ character: Character }> {
    return apiClient.get(`/api/characters/${characterId}`)
  },
  
  // Create character (Phase 7)
  create(data: Omit<Character, 'id'>): Promise<{ character: Character }> {
    return apiClient.post('/api/characters', data)
  },
  
  // Update character (Phase 7)
  update(characterId: string, data: Partial<Character>): Promise<{ character: Character }> {
    return apiClient.patch(`/api/characters/${characterId}`, data)
  },
  
  // Delete character (Phase 7)
  delete(characterId: string): Promise<{ success: boolean }> {
    return apiClient.delete(`/api/characters/${characterId}`)
  },
  
  // Import character (Phase 7)
  import(file: File): Promise<{ character: Character }> {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/api/characters/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  
  // Export character (Phase 7)
  export(characterId: string): Promise<Blob> {
    return apiClient.get(`/api/characters/${characterId}/export`, {
      responseType: 'blob'
    })
  }
}
```

**API Endpoints**:
```
GET    /api/characters              # Get character list
GET    /api/characters/{id}         # Get character details
POST   /api/characters              # Create character (Phase 7)
PATCH  /api/characters/{id}         # Update character (Phase 7)
DELETE /api/characters/{id}         # Delete character (Phase 7)
POST   /api/characters/import       # Import character (Phase 7)
GET    /api/characters/{id}/export  # Export character (Phase 7)
```

**Phase Division**:
- **Phase 6**: Only implement `list()` and `get()` (read-only)
- **Phase 7**: Implement full CRUD + import/export

---

**First half of Chapter 7 complete!**

### 7.6 TTS/ASR API

**Interface Definition**:
```typescript
// src/api/tts.ts
export const ttsAPI = {
  // Get Provider list
  getProviders(): Promise<{ providers: TTSProvider[] }> {
    return apiClient.get('/api/tts/providers')
  },
  
  // Switch Provider
  setProvider(providerId: string): Promise<{ success: boolean; current_provider: string }> {
    return apiClient.post('/api/tts/set-provider', { provider_id: providerId })
  },
  
  // Get voice list
  getVoices(providerId?: string): Promise<{ voices: Voice[] }> {
    return apiClient.get('/api/tts/voices', { params: { provider_id: providerId } })
  }
}

// src/api/asr.ts
export const asrAPI = {
  // Get Provider list
  getProviders(): Promise<{ providers: ASRProvider[] }> {
    return apiClient.get('/api/asr/providers')
  },
  
  // Switch Provider
  setProvider(providerId: string): Promise<{ success: boolean; current_provider: string }> {
    return apiClient.post('/api/asr/set-provider', { provider_id: providerId })
  }
}
```

**API Endpoints**:
```
GET  /api/tts/providers       # Get TTS Provider list
POST /api/tts/set-provider    # Switch TTS Provider
GET  /api/tts/voices          # Get voice list
GET  /api/asr/providers       # Get ASR Provider list
POST /api/asr/set-provider    # Switch ASR Provider
```

**Phase Division**: Implement in Phase 10

---

### 7.7 Live2D API

**Interface Definition**:
```typescript
// src/api/live2d.ts
export const live2dAPI = {
  // Get model list
  getModels(): Promise<{ models: Live2DModel[] }> {
    return apiClient.get('/api/live2d/models')
  },
  
  // Switch model
  setModel(modelId: string): Promise<{ success: boolean; current_model: string }> {
    return apiClient.post('/api/live2d/set-model', { model_id: modelId })
  },
  
  // Upload model
  uploadModel(file: File): Promise<{ success: boolean; model_id: string }> {
    const formData = new FormData()
    formData.append('model', file)
    return apiClient.post('/api/live2d/models', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  
  // Delete model
  deleteModel(modelId: string): Promise<{ success: boolean }> {
    return apiClient.delete(`/api/live2d/models/${modelId}`)
  }
}
```

**API Endpoints**:
```
GET    /api/live2d/models        # Get model list
POST   /api/live2d/set-model     # Switch model
POST   /api/live2d/models        # Upload model
DELETE /api/live2d/models/{id}   # Delete model
```

**Phase Division**: Implement in Phase 8

---

### 7.8 Data Management API

**Interface Definition**:
```typescript
// src/api/data.ts
export const dataAPI = {
  // Export all data
  exportAll(): Promise<Blob> {
    return apiClient.get('/api/data/export', {
      responseType: 'blob'
    })
  },
  
  // Import data
  importData(file: File): Promise<{ success: boolean; imported: number }> {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/api/data/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  
  // Clear data
  clearAll(): Promise<{ success: boolean }> {
    return apiClient.post('/api/data/clear')
  },
  
  // Get statistics
  getStats(): Promise<{ stats: DataStats }> {
    return apiClient.get('/api/data/stats')
  }
}

interface DataStats {
  total_chats: number
  total_messages: number
  total_characters: number
  storage_size: number
}
```

**API Endpoints**:
```
GET  /api/data/export   # Export all data
POST /api/data/import   # Import data
POST /api/data/clear    # Clear data
GET  /api/data/stats    # Get statistics
```

**Phase Division**: Implement in Phase 9

---

### 7.9 Error Handling

#### 7.9.1 Error Types

```typescript
interface APIError {
  code: string
  message: string
  details?: any
}
```

#### 7.9.2 Common Error Codes

| Error Code | HTTP Status | Description | Handling Method |
|-----------|-------------|-------------|-----------------|
| `UNAUTHORIZED` | 401 | Unauthorized | Redirect to login page |
| `FORBIDDEN` | 403 | No permission | Show error notification |
| `NOT_FOUND` | 404 | Resource not found | Show error notification |
| `VALIDATION_ERROR` | 422 | Parameter validation failed | Show field errors |
| `RATE_LIMIT` | 429 | Too many requests | Show rate limit notification |
| `SERVER_ERROR` | 500 | Server error | Show generic error |

#### 7.9.3 Error Handling Example

```typescript
// Usage in component
try {
  await chatsAPI.create({ title: 'New Chat' })
} catch (error) {
  if (error.response?.status === 422) {
    // Parameter validation failed
    showError(error.response.data.message)
  } else if (error.response?.status === 429) {
    // Too many requests
    showError('Too many requests, please try again later')
  } else {
    // Other errors
    showError('Operation failed, please retry')
  }
}
```

**Key Considerations**:
- ⚠️ Unified error handling in response interceptor
- ⚠️ Business errors handled in components
- ⚠️ Show user-friendly error notifications

---

### 7.10 API Usage Examples

**Usage in Store**:
```typescript
// stores/chats.ts
import { chatsAPI } from '@/api/chats'

export const useChatsStore = defineStore('chats', () => {
  const chatList = ref<Chat[]>([])
  
  const loadChats = async () => {
    try {
      const { chats } = await chatsAPI.list()
      chatList.value = chats
    } catch (error) {
      console.error('Failed to load chat list:', error)
      throw error
    }
  }
  
  return { chatList, loadChats }
})
```

**Usage in Component**:
```vue
<script setup lang="ts">
import { chatsAPI } from '@/api/chats'

const handleCreateChat = async () => {
  try {
    const { chat } = await chatsAPI.create({ title: 'New Chat' })
    console.log('Created successfully:', chat)
  } catch (error) {
    console.error('Creation failed:', error)
  }
}
</script>
```

---

**Chapter 7 Complete!**

Next step: Write Chapters 8-11 (Responsive Design + Settings Pages + Authentication + Persistence)

Due to length, chapters will continue to be added in sections. Please confirm to continue?

## 8. Responsive Design

### 8.1 Breakpoint Definitions

**UnoCSS Breakpoint Configuration**:
```typescript
// uno.config.ts
export default defineConfig({
  theme: {
    breakpoints: {
      sm: '640px',   // Mobile
      md: '768px',   // Tablet
      lg: '1024px',  // Desktop
      xl: '1280px',  // Large screen
      '2xl': '1536px' // Extra large screen
    }
  }
})
```

**Usage**:
```html
<!-- Default mobile, md+ tablet, lg+ desktop -->
<div class="w-full md:w-1/2 lg:w-1/3">
  Content
</div>
```

---

### 8.2 Layout Strategy

#### 8.2.1 Main Page Layout

**Desktop (lg+)**:
```
┌─────────────────────────────────────┐
│  Sidebar  │  ChatArea               │
│  (256px)  │  (flex-1)               │
└─────────────────────────────────────┘
```

**Mobile (<lg)**:
```
┌─────────────────────────────────────┐
│  [☰]  ChatArea (Full Screen)        │
│                                     │
│  Sidebar (Drawer, hidden by default) │
└─────────────────────────────────────┘
```

**Implementation Notes**:
```vue
<template>
  <div class="flex h-screen">
    <!-- Sidebar: fixed on desktop, drawer on mobile -->
    <Sidebar 
      :class="{
        'hidden lg:block': !sidebarOpen,
        'fixed inset-0 z-50 lg:relative': sidebarOpen
      }"
    />
    
    <!-- Chat area -->
    <ChatArea class="flex-1" />
    
    <!-- Mobile menu button -->
    <button 
      class="lg:hidden fixed top-4 left-4 z-40"
      @click="toggleSidebar"
    >
      ☰
    </button>
  </div>
</template>
```

---

### 8.3 Component Responsive Adaptation

#### 8.3.1 MessageList (Message List)

```html
<!-- Desktop: fixed width, centered -->
<!-- Mobile: full width -->
<div class="message-list px-4 md:px-8 lg:max-w-4xl lg:mx-auto">
  <MessageItem v-for="msg in messages" :key="msg.id" :message="msg" />
</div>
```

#### 8.3.2 InputBox (Input Box)

```html
<!-- Desktop: fixed height -->
<!-- Mobile: consider virtual keyboard -->
<div class="input-box p-4 md:p-6">
  <textarea 
    class="w-full text-sm md:text-base"
    :rows="isMobile ? 2 : 3"
  />
</div>
```

#### 8.3.3 FoldPanel (Fold Panel)

```html
<!-- Desktop: fixed width 320px -->
<!-- Mobile: full screen -->
<div 
  class="fold-panel"
  :class="{
    'w-80': !isMobile,
    'fixed inset-0': isMobile
  }"
>
  Content
</div>
```

---

### 8.4 Mobile Adaptation

#### 8.4.1 Touch Events

```typescript
// Support touch swipe to close sidebar
let startX = 0

const handleTouchStart = (e: TouchEvent) => {
  startX = e.touches[0].clientX
}

const handleTouchEnd = (e: TouchEvent) => {
  const endX = e.changedTouches[0].clientX
  const diff = endX - startX
  
  // Swipe left more than 100px, close sidebar
  if (diff < -100) {
    closeSidebar()
  }
}
```

#### 8.4.2 Virtual Keyboard Handling

```typescript
// Listen for virtual keyboard popup
window.visualViewport?.addEventListener('resize', () => {
  const keyboardHeight = window.innerHeight - window.visualViewport.height
  
  if (keyboardHeight > 0) {
    // Keyboard shown, adjust input box position
    inputBox.style.bottom = `${keyboardHeight}px`
  } else {
    // Keyboard hidden
    inputBox.style.bottom = '0'
  }
})
```

#### 8.4.3 Safe Area Adaptation

```css
/* Adapt for iPhone notch */
.app {
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}
```

---

### 8.5 Performance Optimization

#### 8.5.1 Image Lazy Loading

```vue
<img 
  :src="placeholder" 
  :data-src="actualImage"
  loading="lazy"
  class="lazy-image"
/>
```

#### 8.5.2 Virtual Scrolling

```typescript
// Use virtual scrolling for long lists
import { useVirtualList } from '@vueuse/core'

const { list, containerProps, wrapperProps } = useVirtualList(
  messages,
  { itemHeight: 80 }
)
```

**Key Considerations**:
- ⚠️ Prioritize touch interaction on mobile
- ⚠️ Adjust layout when virtual keyboard appears
- ⚠️ Use virtual scrolling to optimize long list performance

---

**Chapter 8 Complete!**

## 9. 11 Settings Pages Implementation (Reusing AIRI)

**Fully reuse AIRI's (D:\Coding\GitHub_Resuorse\emotion-robot\airi) implementation (including UI)**

### 9.1 Settings Page Route Table

| Route | Page | Function | Phase | Data Storage |
|-------|------|----------|-------|-------------|
| `/settings/account` | Account Settings | GitHub OAuth login | Phase 7 | Backend API |
| `/settings/airi-card` | Character Card Settings | Character CRUD | Phase 7 | Backend API |
| `/settings/modules/consciousness` | Consciousness Module | LLM Provider management | Phase 6 UI / Phase 10 function | Backend config |
| `/settings/modules/speech` | Speech Module | TTS Provider management | Phase 6 UI / Phase 10 function | Backend config |
| `/settings/modules/hearing` | Hearing Module | ASR Provider management | Phase 6 UI / Phase 10 function | Backend config |
| `/settings/modules/vision` | Vision Module | Vision configuration (reserved) | Phase 10+ | Backend config |
| `/settings/scene` | Scene Settings | Background configuration | Phase 6 | LocalStorage |
| `/settings/models` | Model Settings | Live2D management | Phase 8 | Backend storage |
| `/settings/providers` | Providers | Provider list (read-only) | Phase 6 | Backend config |
| `/settings/data` | Data Management | Import/Export/Clear | Phase 9 | Backend API |
| `/settings/connection` | Connection Settings | WebSocket status | Phase 6 | Real-time status |
| `/settings/system` | System Settings | Language/Theme/Font | Phase 6 | LocalStorage |

---

### 9.2 Account Settings (/settings/account)

**Features**:
- GitHub OAuth login
- Display user info
- Logout

**Interface Definition**:
```typescript
// Dependent Store: userStore
```

**Implementation Notes**:
```vue
<template>
  <div v-if="!userStore.isAuthenticated">
    <button @click="userStore.loginWithGitHub()">
      Login with GitHub
    </button>
  </div>
  
  <div v-else>
    <div>Username: {{ userStore.user.name }}</div>
    <button @click="userStore.logout()">Logout</button>
  </div>
</template>
```

**Phase**: Phase 7

---

### 9.3 Character Card Settings (/settings/airi-card)

**Features**:
- Character list display
- Create/edit/delete characters
- Import/export characters

**Interface Definition**:
```typescript
// Dependent Store: charactersStore
// Dependent API: charactersAPI
```

**Implementation Notes**:
```typescript
// Create character
const handleCreate = async () => {
  await charactersStore.createCharacter({
    name: 'New Character',
    description: 'Character description',
    persona: 'Character persona'
  })
}

// Import character
const handleImport = async (file: File) => {
  await charactersAPI.import(file)
  await charactersStore.loadCharacters()
}
```

**Phase**: Phase 7

---

### 9.4 Consciousness Module (/settings/modules/consciousness)

**Features**:
- Display LLM Provider list
- Switch current Provider (Phase 10)

**Interface Definition**:
```typescript
interface LLMProvider {
  id: string
  name: string
  type: 'cloud' | 'local'
  status: 'available' | 'unavailable'
  models: string[]
}
```

**Implementation Notes**:
```vue
<template>
  <div v-for="provider in providers" :key="provider.id">
    <div>{{ provider.name }}</div>
    <div>Status: {{ provider.status }}</div>
    <button @click="selectProvider(provider.id)">Select</button>
  </div>
</template>
```

**Phase**: Phase 6 (UI framework) / Phase 10 (function implementation)

---

### 9.5 Speech Module (/settings/modules/speech)

**Features**:
- Display TTS Provider list
- Switch Provider
- Select voice

**Implementation Notes**:
```typescript
// Get Provider list
const providers = await ttsAPI.getProviders()

// Switch Provider
await ttsAPI.setProvider(providerId)

// Get voice list
const voices = await ttsAPI.getVoices(providerId)
```

**Phase**: Phase 6 (UI framework) / Phase 10 (function implementation)

---

### 9.6 Hearing Module (/settings/modules/hearing)

**Features**:
- Display ASR Provider list
- Switch Provider

**Implementation Notes**:
```typescript
// Get Provider list
const providers = await asrAPI.getProviders()

// Switch Provider
await asrAPI.setProvider(providerId)
```

**Phase**: Phase 6 (UI framework) / Phase 10 (function implementation)

---

### 9.7 Scene Settings (/settings/scene)

**Features**:

- Upload background image
- Adjust opacity/blur
- Preset backgrounds

**Interface Definition**:
```typescript
// Dependent Store: settingsStore
```

**Implementation Notes**:
```vue
<template>
  <!-- Upload image -->
  <input type="file" @change="handleUpload" accept="image/*" />
  
  <!-- Opacity slider -->
  <input 
    type="range" 
    v-model="opacity" 
    min="0" 
    max="100"
    @change="updateBackground"
  />
  
  <!-- Blur slider -->
  <input 
    type="range" 
    v-model="blur" 
    min="0" 
    max="10"
    @change="updateBackground"
  />
</template>

<script setup>
const handleUpload = async (e) => {
  const file = e.target.files[0]
  await settingsStore.uploadBackgroundImage(file)
}
</script>
```

**Phase**: Phase 6

---

### 9.8 Model Settings (/settings/models)

**Features**:
- Live2D toggle
- Model list
- Upload/delete models

**Implementation Notes**:
```vue
<template>
  <!-- Live2D toggle -->
  <Switch 
    v-model="settingsStore.live2dEnabled"
    @update:modelValue="settingsStore.toggleLive2D"
  />
  
  <!-- Model list -->
  <div v-for="model in models" :key="model.id">
    <div>{{ model.name }}</div>
    <button @click="selectModel(model.id)">Select</button>
    <button @click="deleteModel(model.id)">Delete</button>
  </div>
  
  <!-- Upload model -->
  <input type="file" @change="handleUpload" accept=".zip" />
</template>
```

**Phase**: Phase 8

---

### 9.9 Providers Settings (/settings/providers)

**Features**:
- Display all Provider list (read-only)
- Display health status

**Implementation Notes**:
```vue
<template>
  <div v-for="provider in allProviders" :key="provider.id">
    <div>{{ provider.name }}</div>
    <div>Type: {{ provider.type }}</div>
    <div>Status: {{ provider.status }}</div>
  </div>
</template>
```

**Phase**: Phase 6

---

### 9.10 Data Management (/settings/data)

**Features**:
- Export all data
- Import data
- Clear data
- Display statistics

**Implementation Notes**:
```vue
<template>
  <!-- Statistics -->
  <div>
    <div>Total chats: {{ stats.total_chats }}</div>
    <div>Total messages: {{ stats.total_messages }}</div>
    <div>Total characters: {{ stats.total_characters }}</div>
  </div>
  
  <!-- Export -->
  <button @click="handleExport">Export All Data</button>
  
  <!-- Import -->
  <input type="file" @change="handleImport" accept=".json" />
  
  <!-- Clear -->
  <button @click="handleClear">Clear All Data</button>
</template>

<script setup>
const handleExport = async () => {
  const blob = await dataAPI.exportAll()
  // Download file
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `atri-data-${Date.now()}.json`
  a.click()
}

const handleClear = async () => {
  if (confirm('Are you sure you want to clear all data? This action cannot be undone!')) {
    await dataAPI.clearAll()
  }
}
</script>
```

**Phase**: Phase 9

---

### 9.11 Connection Settings (/settings/connection)

**Features**:
- Display WebSocket connection status
- Manual reconnection
- Display reconnection count

**Implementation Notes**:
```vue
<template>
  <div>
    <div>Status: {{ wsStore.connectionStatus }}</div>
    <div>Reconnection attempts: {{ wsStore.reconnectAttempts }}</div>
    <button 
      @click="wsStore.connect()"
      :disabled="wsStore.connected"
    >
      Manual Reconnect
    </button>
  </div>
</template>
```

**Phase**: Phase 6

---

### 9.12 System Settings (/settings/system)

**Features**:
- Language switching
- Theme switching
- Font size

**Implementation Notes**:
```vue
<template>
  <!-- Language -->
  <select v-model="settingsStore.language" @change="settingsStore.setLanguage">
    <option value="zh-CN">Simplified Chinese</option>
    <option value="en-US">English</option>
  </select>
  
  <!-- Theme -->
  <select v-model="settingsStore.theme" @change="settingsStore.setTheme">
    <option value="light">Light</option>
    <option value="dark">Dark</option>
    <option value="auto">System</option>
  </select>
  
  <!-- Font size -->
  <select v-model="settingsStore.fontSize" @change="settingsStore.setFontSize">
    <option value="small">Small</option>
    <option value="medium">Medium</option>
    <option value="large">Large</option>
  </select>
</template>
```

**Phase**: Phase 6

---

**Chapter 9 Complete!**

## 10. Authentication and Authorization

### 10.1 Authentication Flow

**GitHub OAuth Flow**:
```
1. User clicks "Login with GitHub"
2. Redirect to GitHub authorization page
3. After user authorizes, GitHub redirects to callback URL (with code parameter)
4. Frontend sends code to backend
5. Backend exchanges code for access_token
6. Backend returns JWT token to frontend
7. Frontend stores token in LocalStorage
```

**Implementation Notes**:
```typescript
// stores/user.ts
export const useUserStore = defineStore('user', () => {
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const user = ref<User | null>(null)
  
  const loginWithGitHub = () => {
    const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID
    const redirectUri = `${window.location.origin}/auth/callback`
    const authUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}`
    window.location.href = authUrl
  }
  
  const handleCallback = async (code: string) => {
    const { token: newToken, user: userData } = await authAPI.githubCallback(code)
    token.value = newToken
    user.value = userData
    localStorage.setItem('auth_token', newToken)
  }
  
  const logout = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
  }
  
  return { token, user, loginWithGitHub, handleCallback, logout }
})
```

---

### 10.2 Route Guards

**Implementation Notes**:
```typescript
// router/index.ts
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  
  // Routes requiring authentication
  if (to.meta.requiresAuth && !userStore.token) {
    next('/settings/account')
  } else {
    next()
  }
})
```

**Route Configuration**:
```typescript
const routes = [
  {
    path: '/',
    component: HomePage,
    meta: { requiresAuth: false } // Home page does not require authentication
  },
  {
    path: '/settings/airi-card',
    component: AIRICardSettings,
    meta: { requiresAuth: true } // Character card requires authentication
  }
]
```

---

### 10.3 Request Interceptor

**Adding Token to Request Header**:
```typescript
// api/client.ts
apiClient.interceptors.request.use((config) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers.Authorization = `Bearer ${userStore.token}`
  }
  return config
})
```

**Handling 401 Error**:
```typescript
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      router.push('/settings/account')
    }
    return Promise.reject(error)
  }
)
```

---

### 10.4 Token Refresh

**Implementation Notes**:
```typescript
// Check if token is about to expire
const isTokenExpiringSoon = (token: string): boolean => {
  const payload = JSON.parse(atob(token.split('.')[1]))
  const expiresAt = payload.exp * 1000
  const now = Date.now()
  return expiresAt - now < 5 * 60 * 1000 // Expires within 5 minutes
}

// Refresh token
const refreshToken = async () => {
  const { token: newToken } = await authAPI.refresh()
  token.value = newToken
  localStorage.setItem('auth_token', newToken)
}

// Check in request interceptor
apiClient.interceptors.request.use(async (config) => {
  if (token.value && isTokenExpiringSoon(token.value)) {
    await refreshToken()
  }
  return config
})
```

**Phase Division**: Implement in Phase 7

---

## 11. Data Persistence (Reusing AIRI)

### 11.1 Storage Strategy

| Data Type | Storage Location | Storage Method | Lifecycle |
|-----------|-----------------|----------------|-----------|
| Authentication Token | LocalStorage | `auth_token` | Cleared on logout |
| User Preferences | LocalStorage | `settings` | Permanent |
| Chat List | Backend Database | API | Permanent |
| Character List | Backend Database | API | Permanent |
| Current Chat | Pinia Store | Memory | Cleared on page refresh |
| WebSocket State | Pinia Store | Memory | Cleared on page refresh |

---

### 11.2 LocalStorage Management

**Wrapper Utility**:
```typescript
// utils/storage.ts
export const storage = {
  get<T>(key: string, defaultValue?: T): T | null {
    try {
      const value = localStorage.getItem(key)
      return value ? JSON.parse(value) : defaultValue ?? null
    } catch {
      return defaultValue ?? null
    }
  },
  
  set(key: string, value: any): void {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch (error) {
      console.error('LocalStorage write failed:', error)
    }
  },
  
  remove(key: string): void {
    localStorage.removeItem(key)
  },
  
  clear(): void {
    localStorage.clear()
  }
}
```

**Usage Example**:
```typescript
// stores/settings.ts
export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(storage.get('settings', {
    theme: 'auto',
    language: 'zh-CN',
    fontSize: 'medium'
  }))
  
  watch(settings, (newSettings) => {
    storage.set('settings', newSettings)
  }, { deep: true })
  
  return { settings }
})
```

---

### 11.3 Data Synchronization

**Load Data on Initialization**:

```typescript
// App.vue
onMounted(async () => {
  const userStore = useUserStore()
  const chatsStore = useChatsStore()
  const charactersStore = useCharactersStore()
  
  // If logged in, load user data
  if (userStore.token) {
    await Promise.all([
      chatsStore.loadChats(),
      charactersStore.loadCharacters()
    ])
  }
})
```

**Sync Data Changes to Backend**:

```typescript
// stores/chats.ts
const updateChat = async (chatId: string, updates: Partial<Chat>) => {
  // Optimistic update: update local first
  const chat = chatList.value.find(c => c.id === chatId)
  if (chat) {
    Object.assign(chat, updates)
  }
  
  // Sync to backend
  try {
    await chatsAPI.update(chatId, updates)
  } catch (error) {
    // Rollback on failure
    await loadChats()
    throw error
  }
}
```

---

### 11.4 Offline Support

**Detect Network Status**:
```typescript
// composables/useOnline.ts
export const useOnline = () => {
  const isOnline = ref(navigator.onLine)
  
  const updateOnlineStatus = () => {
    isOnline.value = navigator.onLine
  }
  
  onMounted(() => {
    window.addEventListener('online', updateOnlineStatus)
    window.addEventListener('offline', updateOnlineStatus)
  })
  
  onUnmounted(() => {
    window.removeEventListener('online', updateOnlineStatus)
    window.removeEventListener('offline', updateOnlineStatus)
  })
  
  return { isOnline }
}
```

**Offline Notification**:
```vue
<template>
  <div v-if="!isOnline" class="offline-banner">
    Network connection lost, some features are unavailable
  </div>
</template>

<script setup>
const { isOnline } = useOnline()
</script>
```

---

### 11.5 Data Import/Export

**Export Data**:
```typescript
const exportData = async () => {
  const blob = await dataAPI.exportAll()
  
  // Create download link
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `atri-data-${new Date().toISOString()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
```

**Import Data**:
```typescript
const importData = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  
  await dataAPI.importData(formData)
  
  // Reload data
  await Promise.all([
    chatsStore.loadChats(),
    charactersStore.loadCharacters()
  ])
}
```

---

### 11.6 Caching Strategy

**API Response Caching**:
```typescript
// Cache Provider list (5 minutes)
const providersCache = new Map<string, { data: any; timestamp: number }>()

const getProviders = async (type: 'llm' | 'tts' | 'asr') => {
  const cached = providersCache.get(type)
  const now = Date.now()
  
  if (cached && now - cached.timestamp < 5 * 60 * 1000) {
    return cached.data
  }
  
  const data = await api.getProviders(type)
  providersCache.set(type, { data, timestamp: now })
  return data
}
```

**Key Considerations**:
- ⚠️ Use LocalStorage for sensitive data (Token), not Cookie
- ⚠️ Optimistic update on data changes, rollback on failure
- ⚠️ Disable network-dependent features when offline
- ⚠️ Periodically clean expired cache

**Phase Division**:
- Phase 6: LocalStorage infrastructure
- Phase 7: Authentication token management
- Phase 9: Data import/export

---

**Chapters 10-11 Complete!**

## 12. Performance Optimization

### 12.1 Code Splitting

**Route Lazy Loading**:
```typescript
// router/index.ts
const routes = [
  {
    path: '/chat',
    component: () => import('@/pages/ChatView.vue')
  },
  {
    path: '/settings',
    component: () => import('@/pages/SettingsView.vue'),
    children: [
      {
        path: 'account',
        component: () => import('@/pages/settings/AccountSettings.vue')
      }
      // ... other settings pages
    ]
  }
]
```

**Component Lazy Loading**:
```vue
<script setup>
// Lazy load Live2D component (only load when needed)
const Live2DCanvas = defineAsyncComponent(() => 
  import('@/components/Live2DCanvas.vue')
)
</script>
```

---

### 12.2 Virtual Scrolling

**Long List Optimization**:
```vue
<script setup>
import { useVirtualList } from '@vueuse/core'

const { list, containerProps, wrapperProps } = useVirtualList(
  messages,
  {
    itemHeight: 80,      // Item height
    overscan: 5          // Pre-render 5 items
  }
)
</script>

<template>
  <div v-bind="containerProps" class="message-list">
    <div v-bind="wrapperProps">
      <MessageItem 
        v-for="item in list" 
        :key="item.data.id" 
        :message="item.data"
      />
    </div>
  </div>
</template>
```

---

### 12.3 Image Optimization

**Lazy Loading**:
```vue
<template>
  <img 
    :src="placeholder"
    :data-src="actualImage"
    loading="lazy"
    @load="onImageLoad"
  />
</template>
```

**WebP Format**:
```typescript
// Prefer WebP, fallback to PNG/JPG
const getImageUrl = (path: string) => {
  const supportsWebP = document.createElement('canvas')
    .toDataURL('image/webp')
    .indexOf('data:image/webp') === 0
  
  return supportsWebP 
    ? path.replace(/\.(png|jpg)$/, '.webp')
    : path
}
```

---

### 12.4 Debounce and Throttle

**Input Box Debounce**:
```typescript
import { useDebounceFn } from '@vueuse/core'

const handleInput = useDebounceFn((value: string) => {
  // Handle input
}, 300)
```

**Scroll Event Throttle**:
```typescript
import { useThrottleFn } from '@vueuse/core'

const handleScroll = useThrottleFn(() => {
  // Handle scroll
}, 100)
```

---

### 12.5 Caching Strategy

**Component Caching**:
```vue
<template>
  <router-view v-slot="{ Component }">
    <keep-alive :include="['ChatView', 'SettingsView']">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>
```

**API Response Caching**:
```typescript
// Use Map to cache API responses
const cache = new Map<string, { data: any; timestamp: number }>()

const fetchWithCache = async (key: string, fetcher: () => Promise<any>, ttl = 5 * 60 * 1000) => {
  const cached = cache.get(key)
  const now = Date.now()
  
  if (cached && now - cached.timestamp < ttl) {
    return cached.data
  }
  
  const data = await fetcher()
  cache.set(key, { data, timestamp: now })
  return data
}
```

---

### 12.6 Build Optimization

**Vite Configuration**:
```typescript
// vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'ui-vendor': ['reka-ui'],
          'live2d': ['pixi.js', 'pixi-live2d-display']
        }
      }
    },
    chunkSizeWarningLimit: 1000
  }
})
```

**Tree Shaking**:
```typescript
// Import UnoCSS on demand
import { defineConfig, presetUno } from 'unocss'

export default defineConfig({
  presets: [presetUno()],
  safelist: [] // Only bundle used styles
})
```

---

### 12.7 Performance Monitoring

**Key Metrics**:
```typescript
// Monitor first screen load time
window.addEventListener('load', () => {
  const perfData = performance.getEntriesByType('navigation')[0]
  console.log('First screen load time:', perfData.loadEventEnd - perfData.fetchStart)
})

// Monitor component render time
const startTime = performance.now()
// ... component rendering
const endTime = performance.now()
console.log('Render time:', endTime - startTime)
```

**Performance Targets**:
- First screen load time < 2s
- Route switching < 300ms
- Message rendering < 100ms
- Virtual scrolling frame rate > 60fps

**Phase Division**: Implement in Phase 12

---

## 13. Testing Strategy

### 13.1 Unit Testing

**Test Framework**: Vitest + Vue Test Utils

**Store Testing**:
```typescript
// stores/__tests__/chat.test.ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from '../chat'

describe('ChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })
  
  it('should add message', () => {
    const store = useChatStore()
    store.addMessage({
      id: '1',
      role: 'user',
      content: 'Hello'
    })
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].content).toBe('Hello')
  })
  
  it('should clear messages', () => {
    const store = useChatStore()
    store.addMessage({ id: '1', role: 'user', content: 'Hello' })
    store.clearMessages()
    expect(store.messages).toHaveLength(0)
  })
})
```

**Component Testing**:
```typescript
// components/__tests__/MessageItem.test.ts
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import MessageItem from '../MessageItem.vue'

describe('MessageItem', () => {
  it('should render user message', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '1',
          role: 'user',
          content: 'Hello'
        }
      }
    })
    expect(wrapper.text()).toContain('Hello')
    expect(wrapper.classes()).toContain('user-message')
  })
})
```

---

### 13.2 Integration Testing

**API Integration Testing**:
```typescript
// api/__tests__/chats.test.ts
import { describe, it, expect } from 'vitest'
import { chatsAPI } from '../chats'

describe('ChatsAPI', () => {
  let chatId: string
  
  it('should create chat', async () => {
    const chat = await chatsAPI.create({ title: 'Test Chat' })
    chatId = chat.id
    expect(chat.title).toBe('Test Chat')
  })
  
  it('should get chat list', async () => {
    const chats = await chatsAPI.list()
    expect(chats.length).toBeGreaterThan(0)
  })
  
  it('should delete chat', async () => {
    await chatsAPI.delete(chatId)
    const chats = await chatsAPI.list()
    expect(chats.find(c => c.id === chatId)).toBeUndefined()
  })
})
```

**WebSocket Testing**:
```typescript
// stores/__tests__/websocket.test.ts
import { describe, it, expect, vi } from 'vitest'
import { useWebSocketStore } from '../websocket'

describe('WebSocketStore', () => {
  it('should connect WebSocket', async () => {
    const store = useWebSocketStore()
    await store.connect()
    expect(store.connected).toBe(true)
  })
  
  it('should send message', async () => {
    const store = useWebSocketStore()
    const sendSpy = vi.spyOn(store.ws, 'send')
    
    store.sendMessage({ type: 'chat', content: 'Hello' })
    expect(sendSpy).toHaveBeenCalled()
  })
})
```

---

### 13.3 E2E Testing

**Test Framework**: Playwright

**Login Flow Test**:
```typescript
// e2e/auth.spec.ts
import { test, expect } from '@playwright/test'

test('GitHub login flow', async ({ page }) => {
  await page.goto('http://localhost:5173')
  
  // Click login button
  await page.click('text=Login with GitHub')
  
  // Wait for redirect to GitHub
  await expect(page).toHaveURL(/github\.com/)
  
  // Verify login success
  await expect(page.locator('text=Username')).toBeVisible()
})
```

**Chat Flow Test**:
```typescript
// e2e/chat.spec.ts
import { test, expect } from '@playwright/test'

test('Send message flow', async ({ page }) => {
  await page.goto('http://localhost:5173/chat')
  
  // Input message
  await page.fill('textarea[placeholder="Type a message..."]', 'Hello')
  
  // Send message
  await page.click('button[aria-label="Send"]')
  
  // Verify message display
  await expect(page.locator('text=Hello')).toBeVisible()
  
  // Wait for AI reply
  await expect(page.locator('.assistant-message')).toBeVisible({ timeout: 10000 })
})
```

---

### 13.4 Test Coverage

**Targets**:
- Unit test coverage > 80%
- Integration tests cover core APIs
- E2E tests cover key user flows

**Run Tests**:
```bash
# Unit tests
npm run test:unit

# Integration tests
npm run test:integration

# E2E tests
npm run test:e2e

# Coverage report
npm run test:coverage
```

**Phase Division**: Implement in Phase 12

---

## 14. Deployment and Operations

### 14.1 Build Configuration

**Production Build**:
```bash
# Build command
npm run build

# Output directory
dist/
  ├── index.html
  ├── assets/
  │   ├── index-[hash].js
  │   ├── index-[hash].css
  │   └── vendor-[hash].js
  └── models/  # Live2D model files
```

**Environment Variables**:
```bash
# .env.production
VITE_API_BASE_URL=https://api.example.com
VITE_WS_URL=wss://api.example.com/ws
VITE_GITHUB_CLIENT_ID=your_client_id
```

---

### 14.2 Docker Deployment

**Dockerfile**:
```dockerfile
# Build stage
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Run stage
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Nginx Configuration**:
```nginx
server {
  listen 80;
  server_name localhost;
  root /usr/share/nginx/html;
  index index.html;

  # SPA route support
  location / {
    try_files $uri $uri/ /index.html;
  }

  # API proxy
  location /api {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }

  # WebSocket proxy
  location /ws {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
  }

  # Static resource caching
  location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
  }
}
```

---

### 14.3 CI/CD Pipeline

**GitHub Actions**:

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: 18
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run tests
        run: npm run test:unit
      
      - name: Build
        run: npm run build
        env:
          VITE_API_BASE_URL: ${{ secrets.API_BASE_URL }}
          VITE_WS_URL: ${{ secrets.WS_URL }}
      
      - name: Build Docker image
        run: docker build -t atri-webui:latest .
      
      - name: Push to registry
        run: |
          echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
          docker push atri-webui:latest
```

---

### 14.4 Monitoring and Alerting

**Error Monitoring**:

```typescript
// Integrate Sentry
import * as Sentry from '@sentry/vue'

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE,
  integrations: [
    new Sentry.BrowserTracing({
      routingInstrumentation: Sentry.vueRouterInstrumentation(router)
    })
  ],
  tracesSampleRate: 0.1
})
```

**Performance Monitoring**:
```typescript
// Report performance metrics
const reportPerformance = () => {
  const perfData = performance.getEntriesByType('navigation')[0]
  
  fetch('/api/metrics', {
    method: 'POST',
    body: JSON.stringify({
      loadTime: perfData.loadEventEnd - perfData.fetchStart,
      domReady: perfData.domContentLoadedEventEnd - perfData.fetchStart,
      firstPaint: performance.getEntriesByName('first-paint')[0]?.startTime
    })
  })
}
```

---

### 14.5 Log Management

**Log Levels**:
```typescript
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3
}

class Logger {
  private level: LogLevel = LogLevel.INFO
  
  debug(message: string, ...args: any[]) {
    if (this.level <= LogLevel.DEBUG) {
      console.debug(`[DEBUG] ${message}`, ...args)
    }
  }
  
  info(message: string, ...args: any[]) {
    if (this.level <= LogLevel.INFO) {
      console.info(`[INFO] ${message}`, ...args)
    }
  }
  
  warn(message: string, ...args: any[]) {
    if (this.level <= LogLevel.WARN) {
      console.warn(`[WARN] ${message}`, ...args)
    }
  }
  
  error(message: string, ...args: any[]) {
    if (this.level <= LogLevel.ERROR) {
      console.error(`[ERROR] ${message}`, ...args)
      // Report to monitoring system
      Sentry.captureException(new Error(message))
    }
  }
}

export const logger = new Logger()
```

---

### 14.6 Backup and Recovery

**Data Backup**:
```typescript
// Export user data
const exportUserData = async () => {
  const data = {
    settings: localStorage.getItem('settings'),
    chats: await db.chats.toArray(),
    characters: await db.characters.toArray()
  }
  
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  
  const a = document.createElement('a')
  a.href = url
  a.download = `atri-backup-${Date.now()}.json`
  a.click()
}

// Import user data
const importUserData = async (file: File) => {
  const text = await file.text()
  const data = JSON.parse(text)
  
  localStorage.setItem('settings', data.settings)
  await db.chats.bulkPut(data.chats)
  await db.characters.bulkPut(data.characters)
}
```

## 15. Summary

### 15.1 Core Features

**Dual-mode Main Page**:
- Mode A (ChatGPT style): Clean dialogue interface, no Live2D
- Mode B (AIRI style): Live2D + fold panel, immersive experience
- Seamless switching via Live2D toggle

**Centralized Architecture**:
- Backend manages: Provider configuration, API keys, model parameters
- Frontend manages: UI preferences, themes, keyboard shortcuts, layout
- Clear responsibility boundaries, reduced maintenance costs

**Modular Design**:

- 7 Pinia Stores: user, chat, websocket, characters, settings, etc.
- 11 Settings pages: general, characters, Live2D, speech, keyboard shortcuts, etc.
- Reusable components: MessageItem, CharacterCard, FoldPanel, etc.

---

### 15.2 Technical Highlights

**Performance Optimization**:
- Route lazy loading: Reduce first screen load time
- Virtual scrolling: Optimize long list rendering
- Code splitting: vendor, ui, live2d independently packaged
- Image lazy loading: Reduce bandwidth consumption

**User Experience**:
- Responsive design: Adapt to mobile/tablet/desktop
- Dark mode: Eye-friendly and aesthetically pleasing
- Keyboard shortcut support: Improve operation efficiency
- Offline cache: IndexedDB stores chat history

---

### 15.3 Phase Division Suggestions (Draft, must consider current status)

**Phase 6 (Core Features)**:

- Routing system (vue-router)
- Basic layout (ChatView, SettingsView)
- Core Stores (user, chat, websocket)
- Login authentication (GitHub OAuth)

**Phase 7 (Chat Features)**:
- Chat interface (MessageList, MessageItem, InputBox)
- WebSocket communication (message send/receive, heartbeat/reconnection)
- Chat management (create/delete/switch conversations)
- Character management (select character, character cards)

**Phase 8 (Live2D Integration)**:
- Live2D rendering (pixi.js + pixi-live2d-display)
- Model loading (local/remote models)
- Expression actions (triggered by messages)
- Fold panel (character selector + chat history)

**Phase 9 (Settings Pages)**:
- 11 settings pages (general, characters, Live2D, speech, etc.)
- Settings persistence (LocalStorage)
- Theme switching (light/dark)
- Keyboard shortcut configuration

**Phase 10 (Responsive Design)**:
- Mobile adaptation (breakpoints, layout)
- Tablet adaptation (sidebar collapse)
- Touch gestures (swipe, long press)

**Phase 11 (Performance Optimization)**:
- Code splitting (route lazy loading, component lazy loading)
- Virtual scrolling (long list optimization)
- Image optimization (lazy loading, WebP)
- Caching strategy (component cache, API cache)

**Phase 12 (Testing)**:
- Unit tests (Stores, components)
- Integration tests (API, WebSocket)
- E2E tests (login, chat flow)

**Phase 13 (Deployment and Operations)**:
- Docker image build
- CI/CD pipeline (GitHub Actions)
- Monitoring and alerting (Sentry)
- Log management

---

### 15.4 Reference Documents

**Design Documents**:
- `docs/Phase_X划分讨论.md` (Round 13-17)
- `docs/总结_前端对话历史.md`
- `docs/前端设计对话历史.md`
- `docs/Live-2d设计文档.md`

**Reference Code**:
- `atri-webui/src/` (current project)
- `airi/packages/` (AIRI core packages)
- `airi/apps/stage-web/` (AIRI frontend)

---

### 15.5 Future Work

**Feature Enhancement**:
- Multi-modal support (images, voice, video)
- Plugin system (custom feature extensions)
- Collaboration features (multi-person dialogue, share conversations)
- Data analysis (conversation statistics, usage habits)

**Performance Optimization**:
- Service Worker (offline support)
- WebAssembly (computation-intensive tasks)
- HTTP/3 (faster network transfer)

**User Experience**:

- Accessibility support (ARIA labels, keyboard navigation)
- Internationalization (multi-language support)
- Personalized recommendations (character recommendations, theme recommendations)
