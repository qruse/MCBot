import { labels } from "./messages";

export const krw = (value: number) => `₩${Math.round(value).toLocaleString("ko-KR")}`;
export const signed = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${krw(Math.abs(value))}`;
export const percent = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(4)}%`;
export const time = (value?: number | null) => value ? new Date(value).toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
export const label = (value: string) => labels[value] ?? "상태 확인 필요";
