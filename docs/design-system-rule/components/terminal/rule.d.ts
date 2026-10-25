// Rule terminal primitives — props contracts. Runtime: rule.jsx → window.Rule
export type Theme = 'dark' | 'light';
export type ToolState = 'running' | 'done' | 'failed';
export type OutcomeKind = 'ok' | 'warn' | 'err';
export interface TermProps { theme?: Theme; cols?: number; children?: React.ReactNode }
export interface TurnRuleProps { n: number; cols?: number }
export interface YouProps { children: React.ReactNode }
/** Each child is one wrapped line; the first gets ■. */
export interface AgentProps { children: React.ReactNode }
export interface HeadingProps { children: string }
export interface ToolProps { name: string; args?: string; state?: ToolState }
export interface ResultProps { children: React.ReactNode; more?: number; error?: boolean; keyName?: string }
export interface ThinkingProps { secs?: number; children?: React.ReactNode }
export interface WorkingProps { verb?: string; secs?: number; frame?: 0 | 1 | 2 | 3 }
export interface OutcomeProps { kind?: OutcomeKind; subject: string; detail?: string }
export interface FactsProps { items: string[] }
export interface LabelledProps { label: string; upper?: boolean; children: React.ReactNode }
export interface FrameProps { edge?: 'rule' | 'accent'; title?: string; cols?: number; children?: React.ReactNode }
export interface InputBoxProps { typed?: string; hint?: string; cols?: number }
export interface StatusRowProps { left?: string; model?: string; cwd?: string; ctx?: string; cols?: number }
export interface PopupProps { items: [string, string][]; selected?: number }
export interface DialogProps { title: string; body?: React.ReactNode[]; question?: string; options: string[]; selected?: number; cols?: number }
export interface FootingProps extends InputBoxProps, StatusRowProps { dialog?: React.ReactNode; popup?: React.ReactNode }
