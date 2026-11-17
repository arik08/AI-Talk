export type AvatarSet = 'bot' | 'face' | 'orb' | 'crest';
export type AvatarSpec = { set: AvatarSet; variant: number };
export type Mood = 'calm' | 'agree' | 'skeptical' | 'heated' | 'curious' | 'surprised' | 'amused' | 'thinking';
export type AvatarState = 'idle' | 'listening' | 'ready' | 'speaking' | 'searching' | 'cut';

export interface Persona {
  id?: string;
  name: string;
  title: string;
  expertise: string;
  personality: string;
  speech: string;
  viewpoint: string;
  claims: string[];
  concede: string;
  hidden: string;
  color: string;
  avatar: AvatarSpec;
  tags: string[];
  model?: string;
  effort?: string;
}

export interface ModelInfo {
  id: string;
  label: string;
  efforts: string[];
  default_effort: string;
  search: boolean;
  price: { in: number; cached: number; write: number; out: number } | null;
  note: string;
}

export interface Status {
  provider: string;
  ready: boolean;
  message: string;
  models: ModelInfo[];
  defaults: { model: string; effort: string; compact_threshold: number; hidden_agenda: boolean };
  network?: { shared: boolean; port: number; addresses: string[]; code: boolean };
}

export interface DebateSummary {
  id: string;
  topic: string;
  created: string;
  state: string;
  turns: number;
  seconds: number;
  provider: string;
  cost: number;
  participants: { name: string; color?: string; avatar?: AvatarSpec }[];
}

export interface DebateEvent {
  i: number;
  t: number;
  type: string;
  [key: string]: any;
}

export interface DebateRecord {
  id: string;
  config: any;
  moderator: Persona | null;
  provider: string;
  created: string;
  state: string;
  live: boolean;
  events: DebateEvent[];
  speeches: any[];
  summary: any;
  minutes?: any;
  briefing: string;
  turns?: number;
  seconds?: number;
}

export const MOOD_LABEL: Record<Mood, string> = {
  calm: '평온', agree: '수긍', skeptical: '못마땅', heated: '격앙',
  curious: '궁금', surprised: '놀람', amused: '웃음', thinking: '고민',
};

export const INTENT_LABEL: Record<string, string> = {
  rebut: '반박', add: '보충', ask: '질문', agree: '동의', shift: '화제 전환', answer: '답변',
  open: '개회', statement: '모두발언', moderate: '진행', closing: '마무리 발언', wrap: '정리',
};

export const PALETTE = ['#E0764A', '#5FB6A8', '#8FA8E8', '#C98BD9', '#9CC766', '#E36F8A', '#5FA8D8', '#D9A441', '#C9B38A', '#7FD1C0'];
