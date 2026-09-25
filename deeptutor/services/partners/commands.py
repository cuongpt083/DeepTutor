"""Slash commands for partner chat surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import shlex
from typing import Any, Callable

from deeptutor.agents._shared.tool_composition import default_optional_tools
from deeptutor.partners.bus.events import InboundMessage
from deeptutor.services.partners.sessions import PartnerSessionStore


@dataclass(frozen=True)
class PartnerCommandSpec:
    command: str
    description: str
    arg_hint: str = ""


@dataclass(frozen=True)
class PartnerCommandResult:
    content: str


BUILTIN_PARTNER_COMMANDS: tuple[PartnerCommandSpec, ...] = (
    PartnerCommandSpec("/help", "Show available partner commands."),
    PartnerCommandSpec("/new", "Archive this conversation and start a fresh one."),
    PartnerCommandSpec("/branch", "Archive this conversation and continue in a copy."),
    PartnerCommandSpec("/stop", "Stop the reply that's currently being generated."),
    PartnerCommandSpec("/sessions", "List this partner's conversations and their IDs."),
    PartnerCommandSpec("/resume", "Reopen an archived conversation.", "<session ID>"),
    PartnerCommandSpec("/delete", "Delete a conversation permanently.", "<session ID>"),
    PartnerCommandSpec("/status", "Show partner, session, model, and tool status."),
    PartnerCommandSpec("/history", "Show recent messages in this conversation.", "[n]"),
    PartnerCommandSpec("/tool", "Show or change enabled tools.", "[on|off <name>|reset]"),
    PartnerCommandSpec(
        "/link",
        "Connect this chat account to your DeepTutor account.",
        "<code from the web app>",
    ),
    PartnerCommandSpec(
        "/pair",
        "Ghép nối tài khoản CRM với bot.",
        "<mã kết nối>",
    ),
    PartnerCommandSpec(
        "/customers",
        "Thống kê số lượng và danh sách khách hàng trên CRM.",
    ),
    PartnerCommandSpec(
        "/birthdays",
        "Thống kê danh sách khách hàng sắp đến sinh nhật.",
    ),
    PartnerCommandSpec(
        "/tasks",
        "Xem danh sách nhiệm vụ chăm sóc khách hàng hôm nay.",
    ),
    PartnerCommandSpec(
        "/checkin",
        "Ghi nhận nhật ký sức khỏe & tính điểm Bioclock.",
        "<tên_khách> [ngày] nuoc=<cốc> bua=<bữa> tap=<phút> baihoc=<1/0>",
    ),
    PartnerCommandSpec(
        "/meal",
        "Tra cứu calo kỳ diệu & cấu trúc 5 bữa ăn cho khách hàng.",
        "<tên_khách>",
    ),
    PartnerCommandSpec(
        "/report",
        "Xem báo cáo tiến độ, biến thiên cân nặng, tỷ lệ mỡ và streak.",
        "<tên_khách>",
    ),
    PartnerCommandSpec(
        "/script",
        "Tạo kịch bản (talking point) chăm sóc khách hàng theo ngày/tình huống.",
        "<tên_khách> <chủ_đề_hoặc_ngày>",
    ),
)


def partner_command_palette() -> list[dict[str, str]]:
    return [
        {
            "command": spec.command,
            "description": spec.description,
            "arg_hint": spec.arg_hint,
        }
        for spec in BUILTIN_PARTNER_COMMANDS
    ]


def build_partner_help_text() -> str:
    lines = ["Partner commands:"]
    for spec in BUILTIN_PARTNER_COMMANDS:
        command = f"{spec.command} {spec.arg_hint}".rstrip()
        lines.append(f"{command} - {spec.description}")
    lines.append("/clear - Alias for /new.")
    return "\n".join(lines)


def looks_like_partner_command(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) > 1 and stripped.startswith("/") and stripped[1].isalpha()


def _normalize_vn(text: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return (
        without_diacritics.lower()
        .replace("đ", "d")
        .replace("Đ", "d")
        .strip()
    )


class PartnerCommandHandler:
    def __init__(
        self,
        *,
        partner_id: str,
        config: Any,
        store: PartnerSessionStore,
        save_config: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.partner_id = partner_id
        self.config = config
        self.store = store
        self.save_config = save_config

    def dispatch(self, msg: InboundMessage) -> Any:
        raw = msg.content.strip()
        if not looks_like_partner_command(raw):
            return self._dispatch_conversational(msg)
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            return PartnerCommandResult(f"Could not parse command: {exc}")
        if not parts:
            return None

        command = parts[0].lower().split("@", 1)[0]
        args = parts[1:]
        if command == "/help":
            return PartnerCommandResult(build_partner_help_text())
        if command in {"/new", "/clear"}:
            return self._new(msg)
        if command == "/branch":
            return self._branch(msg)
        if command == "/stop":
            return PartnerCommandResult("There's nothing being generated to stop.")
        if command == "/sessions":
            return self._sessions()
        if command == "/resume":
            return self._resume(args)
        if command == "/delete":
            return self._delete(args)
        if command == "/status":
            return self._status(msg)
        if command == "/history":
            return self._history(msg, args)
        if command == "/tool":
            return self._tool(args)
        if command == "/link":
            return self._link(msg, args)
        if command == "/pair":
            return self._pair(msg, args)
        if command in {"/customers", "/khachhang", "/customer"}:
            return self._customers(msg, args)
        if command in {"/birthdays", "/birthday", "/sinhnhat"}:
            return self._birthdays(msg, args)
        if command in {"/tasks", "/task", "/congviec"}:
            return self._tasks(msg, args)
        if command in {"/checkin", "/ci"}:
            return self._checkin(msg, args)
        if command in {"/meal", "/thucdon"}:
            return self._meal(msg, args)
        if command in {"/report", "/baocao", "/tiendo", "/progress"}:
            return self._report(msg, args)
        if command in {"/script", "/talkingpoint", "/tp", "/kichban", "/baihoc"}:
            return self._script(msg, args)
        return PartnerCommandResult(f"Unknown command: {parts[0]}\n\n{build_partner_help_text()}")

    async def _pair(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Pair this chat account with NutriTech CRM using a pairing code."""
        if (msg.metadata or {}).get("is_group"):
            return PartnerCommandResult(
                "Vui lòng gửi lệnh /pair trong tin nhắn riêng 1-1 với bot để đảm bảo an toàn."
            )
        if not args:
            return PartnerCommandResult(
                "Cách dùng: /pair <mã_kết_nối>\n"
                "Ví dụ: /pair ABCD2345\n\n"
                "Mã gồm 8 ký tự lấy từ trang /account trên web CRM (có hiệu lực trong 10 phút)."
            )
        code = args[0].strip().upper()
        try:
            from deeptutor.services.mcp import get_mcp_manager

            mgr = get_mcp_manager()
            await mgr.ensure_started()

            target_conn = None
            for key, conn in mgr._connections.items():
                for adapter in conn.adapters:
                    if getattr(adapter, "_original_name", "") == "channel_pair":
                        target_conn = (conn.owner, conn.name)
                        break
                if target_conn:
                    break

            if not target_conn:
                return PartnerCommandResult(
                    "Không tìm thấy công cụ ghép nối CRM qua MCP. Vui lòng kiểm tra cấu hình MCP."
                )

            result_str = await mgr.call_tool(
                owner=target_conn[0],
                server_name=target_conn[1],
                tool_name="channel_pair",
                arguments={
                    "code": code,
                    "platform": msg.channel,
                    "platformUserId": str(msg.sender_id),
                },
                timeout=15,
            )
            import json

            try:
                data = json.loads(result_str)
                if isinstance(data, dict):
                    if data.get("success"):
                        return PartnerCommandResult(
                            str(data.get("message") or f"Ghép nối tài khoản thành công! HLV {data.get('coachName', '')}")
                        )
                    else:
                        return PartnerCommandResult(
                            str(data.get("error") or "Ghép nối không thành công: Mã không hợp lệ hoặc đã hết hạn.")
                        )
            except Exception:
                pass
            return PartnerCommandResult(str(result_str))
        except Exception as exc:
            return PartnerCommandResult(f"Lỗi khi thực hiện ghép nối kênh: {exc}")

    async def _call_crm_tool(
        self,
        msg: InboundMessage,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[bool, Any]:
        """Invoke a NutriTech CRM tool via MCP."""
        try:
            from deeptutor.services.mcp import get_mcp_manager

            mgr = get_mcp_manager()
            await mgr.ensure_started()

            target_conn = None
            for key, conn in mgr._connections.items():
                for adapter in conn.adapters:
                    if getattr(adapter, "_original_name", "") == tool_name:
                        target_conn = (conn.owner, conn.name)
                        break
                if target_conn:
                    break

            if not target_conn:
                return False, f"Không tìm thấy công cụ CRM `{tool_name}` qua MCP. Vui lòng kiểm tra cấu hình MCP."

            args = dict(arguments or {})
            args.setdefault("platform", msg.channel)
            args.setdefault("platformUserId", str(msg.sender_id))

            result_str = await mgr.call_tool(
                owner=target_conn[0],
                server_name=target_conn[1],
                tool_name=tool_name,
                arguments=args,
                timeout=15,
            )
            res_str = str(result_str)
            if "write window is closed" in res_str.lower() or "write_window_expired" in res_str.lower():
                return False, (
                    "🔒 **Cửa sổ ghi dữ liệu CRM (Write Window) đang đóng!**\n\n"
                    "Để bảo vệ an toàn dữ liệu khách hàng, tính năng ghi nhận/sửa đổi trên bot cần mở cửa sổ ghi.\n\n"
                    "👉 **Cách mở:**\n"
                    "1. Truy cập trang Web CRM tại mục **Tài khoản** (`/account`)\n"
                    "2. Tại danh sách **Kênh kết nối**, bấm nút **'Mở cửa sổ ghi'** (thời hạn 60 phút).\n"
                    "Sau đó bạn có thể thực hiện lại thao tác này bình thường."
                )
            if res_str.startswith("Tool error:"):
                return False, f"⚠️ {res_str}"

            import json

            try:
                data = json.loads(result_str)
                if isinstance(data, dict) and data.get("error"):
                    return False, str(data.get("error"))
                return True, data
            except Exception:
                return True, result_str
        except Exception as exc:
            err_msg = str(exc)
            if "chưa được liên kết" in err_msg.lower():
                return False, (
                    "⚠️ Tài khoản chat này chưa được liên kết với Huấn luyện viên nào trên CRM.\n"
                    "👉 Vui lòng đăng nhập CRM, bấm **'Tạo mã kết nối'** tại trang Tài khoản và gửi cho bot theo cú pháp:\n"
                    "`/pair <mã_8_ký_tự>`"
                )
            return False, f"Lỗi khi truy vấn CRM ({tool_name}): {exc}"

    async def _customers(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Show customer statistics and list from NutriTech CRM."""
        ok, res = await self._call_crm_tool(msg, "customer_list")
        if not ok:
            return PartnerCommandResult(str(res))

        customers = res if isinstance(res, list) else []
        if not customers:
            return PartnerCommandResult(
                "📊 **THỐNG KÊ KHÁCH HÀNG CRM**\n\n"
                "Hiện tại danh sách khách hàng chính thức của bạn đang trống (0 khách hàng).\n\n"
                "💡 **Gợi ý hành động (DMO):**\n"
                "- Thêm khách hàng tiềm năng (Leads) mới trên Web CRM.\n"
                "- Thực hiện khảo sát 15 phút, quét 9 chỉ số Tanita và tính Calo kỳ diệu để chuyển đổi khách hàng tiềm năng thành khách hàng chính thức."
            )

        total = len(customers)
        prog_labels = {
            "co_nuoc_mo": "Cơ – Nước – Mỡ (Giảm mỡ tăng cơ)",
            "dinh_duong_te_bao": "Dinh dưỡng tế bào (Tăng cân / Phục hồi)",
            "bua_an_lanh_manh": "Bữa ăn lành mạnh (Duy trì / Tối ưu)",
        }
        prog_counts: dict[str, int] = {}
        rfm_counts: dict[str, int] = {"active": 0, "at_risk": 0, "disengaged": 0}

        for c in customers:
            p = str(c.get("program") or "khac")
            prog_counts[p] = prog_counts.get(p, 0) + 1
            rfm = str(c.get("rfmStatus") or c.get("rfm_status") or "active").lower()
            if rfm in rfm_counts:
                rfm_counts[rfm] += 1
            else:
                rfm_counts[rfm] = 1

        lines = [
            f"📊 **BÁO CÁO THỐNG KÊ KHÁCH HÀNG CRM**",
            f"👤 Huấn luyện viên: Telegram ID `{msg.sender_id}`",
            f"👥 **Tổng số khách hàng quản lý: {total} khách hàng**\n",
            "🥗 **Phân loại theo Chương trình dinh dưỡng:**",
        ]
        for p_key, count in prog_counts.items():
            label = prog_labels.get(p_key, f"Chương trình khác ({p_key})")
            pct = round((count / total) * 100, 1)
            lines.append(f"- **{label}:** {count} khách hàng ({pct}%)")

        lines.extend([
            "\n🎯 **Phân khúc chăm sóc (RFM):**",
            f"- 🟢 **Đang hoạt động tốt (`active`):** {rfm_counts.get('active', 0)} khách hàng",
            f"- 🟡 **Có nguy cơ giảm tương tác (`at_risk`):** {rfm_counts.get('at_risk', 0)} khách hàng",
            f"- 🔴 **Cần kích hoạt lại (`disengaged`):** {rfm_counts.get('disengaged', 0)} khách hàng",
            "\n📋 **Danh sách chi tiết:**",
        ])

        for i, c in enumerate(customers, 1):
            name = c.get("name") or "Khách hàng"
            phone = c.get("phone") or "Chưa có SĐT"
            prog = prog_labels.get(c.get("program"), c.get("program") or "Cơ bản")
            tier = str(c.get("packageTier") or c.get("package_tier") or "Tiêu chuẩn").capitalize()
            rfm = str(c.get("rfmStatus") or c.get("rfm_status") or "active")
            rfm_icon = "🟢" if rfm == "active" else ("🟡" if rfm == "at_risk" else "🔴")
            lines.append(f"{i}. **{name}** ({phone}) – Gói {tier} – {rfm_icon} `{rfm}`")

        lines.append(
            "\n💡 *Gõ `/birthdays` để xem danh sách khách hàng sắp đến sinh nhật hoặc `/tasks` để xem nhiệm vụ hôm nay.*"
        )
        return PartnerCommandResult("\n".join(lines))

    async def _birthdays(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Show customers with upcoming birthdays from NutriTech CRM."""
        from datetime import date, datetime

        ok, res = await self._call_crm_tool(msg, "customer_list")
        if not ok:
            return PartnerCommandResult(str(res))

        customers = res if isinstance(res, list) else []
        if not customers:
            return PartnerCommandResult(
                "🎂 **THỐNG KÊ SINH NHẬT KHÁCH HÀNG**\n\n"
                "Hiện tại danh sách khách hàng của bạn chưa có dữ liệu nào trên CRM."
            )

        today = date.today()
        bday_items = []

        for c in customers:
            b_str = c.get("birthDate") or c.get("birth_date")
            if not b_str:
                continue
            try:
                dt = datetime.strptime(str(b_str)[:10], "%Y-%m-%d").date()
                try:
                    bday_this_year = dt.replace(year=today.year)
                except ValueError:
                    bday_this_year = date(today.year, 3, 1)

                if bday_this_year < today:
                    try:
                        next_bday = dt.replace(year=today.year + 1)
                    except ValueError:
                        next_bday = date(today.year + 1, 3, 1)
                else:
                    next_bday = bday_this_year

                days_left = (next_bday - today).days
                turning_age = next_bday.year - dt.year
                bday_items.append({
                    "customer": c,
                    "birth_date": dt,
                    "next_birthday": next_bday,
                    "days_left": days_left,
                    "turning_age": turning_age,
                })
            except Exception:
                continue

        if not bday_items:
            return PartnerCommandResult(
                "🎂 **THỐNG KÊ SINH NHẬT KHÁCH HÀNG**\n\n"
                "Chưa có khách hàng nào được cập nhật ngày sinh (`birthDate`) trong hồ sơ CRM.\n"
                "💡 *Hãy vào chi tiết hồ sơ khách hàng trên Web CRM để bổ sung ngày sinh nhật nhằm kích hoạt tính năng nhắc nhở tự động.*"
            )

        bday_items.sort(key=lambda x: x["days_left"])
        upcoming = [x for x in bday_items if x["days_left"] <= 30]

        lines = [
            f"🎂 **BÁO CÁO SINH NHẬT KHÁCH HÀNG (30 NGÀY TỚI)**",
            f"📅 Hôm nay: Ngày `{today.strftime('%d/%m/%Y')}`\n",
        ]

        if not upcoming:
            closest = bday_items[0]
            c = closest["customer"]
            d_str = closest["next_birthday"].strftime("%d/%m")
            lines.append(
                f"Trong 30 ngày tới không có khách hàng nào đến ngày sinh nhật.\n\n"
                f"🎯 **Sinh nhật gần nhất tiếp theo:**\n"
                f"- Khách hàng: **{c.get('name')}** ({c.get('phone', 'N/A')})\n"
                f"- Ngày sinh: `{closest['birth_date'].strftime('%d/%m/%Y')}` (Sinh nhật: `{d_str}`, còn **{closest['days_left']} ngày** nữa – Sắp tròn **{closest['turning_age']} tuổi**)."
            )
        else:
            lines.append(f"Có **{len(upcoming)} khách hàng** sắp đến ngày sinh nhật:\n")
            for i, item in enumerate(upcoming, 1):
                c = item["customer"]
                name = c.get("name") or "Khách hàng"
                phone = c.get("phone") or "Chưa có SĐT"
                days_left = item["days_left"]
                turning_age = item["turning_age"]
                b_date = item["birth_date"].strftime("%d/%m/%Y")
                next_date_str = item["next_birthday"].strftime("%d/%m")

                if days_left == 0:
                    countdown_text = "🎉 **HÔM NAY LÀ SINH NHẬT!**"
                elif days_left == 1:
                    countdown_text = f"⏰ **NGÀY MAI ({next_date_str})**"
                else:
                    countdown_text = f"⏳ Còn **{days_left} ngày** (ngày {next_date_str})"

                lines.append(
                    f"{i}. **{name}** ({phone})\n"
                    f"   - 📅 Ngày sinh: `{b_date}` (Sắp tròn **{turning_age} tuổi**)\n"
                    f"   - {countdown_text}\n"
                    f"   - 🥗 Gói: `{c.get('packageTier') or 'Cơ bản'}` | Trạng thái: `{c.get('rfmStatus') or 'active'}`\n"
                    f"   - 💡 **Gợi ý DMO:** Gửi thiệp chúc mừng sinh nhật, tặng 1 buổi đo quét Tanita miễn phí cho người thân hoặc voucher quà tặng bữa ăn lành mạnh.\n"
                )

        return PartnerCommandResult("\n".join(lines))

    async def _tasks(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Show care tasks from NutriTech CRM."""
        ok_today, res_today = await self._call_crm_tool(msg, "task_list_today")
        ok_overdue, res_overdue = await self._call_crm_tool(msg, "task_get_overdue")

        if not ok_today:
            return PartnerCommandResult(str(res_today))

        tasks_today = res_today if isinstance(res_today, list) else []
        tasks_overdue = res_overdue if isinstance(res_overdue, list) else []

        total_pending = len([t for t in tasks_today if t.get("status") == "pending"]) + len(tasks_overdue)

        lines = [
            f"📋 **NHIỆM VỤ CHĂM SÓC KHÁCH HÀNG (HÔM NAY)**",
            f"⏳ Tổng số việc cần xử lý: **{total_pending} nhiệm vụ**\n",
        ]

        if tasks_overdue:
            lines.append("🔴 **Nhiệm vụ quá hạn chưa hoàn thành:**")
            for t in tasks_overdue:
                lines.append(f"- ⚠️ **{t.get('title')}** (Hạn: `{t.get('dueDate')}`)")
            lines.append("")

        if tasks_today:
            lines.append("📌 **Nhiệm vụ trong ngày hôm nay:**")
            for t in tasks_today:
                status_icon = "✅" if t.get("status") == "done" else "⭕"
                lines.append(f"- {status_icon} **{t.get('title')}** (`{t.get('priority', 'normal')}`)")
        else:
            lines.append("🎉 *Hôm nay không có nhiệm vụ chăm sóc tồn đọng. Bạn đã hoàn thành xuất sắc DMO!*")

        return PartnerCommandResult("\n".join(lines))

    async def _resolve_customer(
        self, msg: InboundMessage, query: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Match customer by name, phone, or id against the coach's customer list."""
        ok, res = await self._call_crm_tool(msg, "customer_list")
        if not ok:
            return None, str(res)
        customers = res if isinstance(res, list) else []
        if not customers:
            return None, (
                "⚠️ Danh sách khách hàng trên CRM của bạn hiện đang trống.\n"
                "💡 Vui lòng thêm khách hàng tiềm năng và chuyển đổi trên Web CRM trước khi thực hiện thao tác này."
            )
        q = query.strip()
        q_norm = _normalize_vn(q)
        q_lower = q.lower()

        # Try exact ID match first
        for c in customers:
            if str(c.get("id", "")).lower() == q_lower:
                return c, None

        # Filter matches
        matches = []
        for c in customers:
            name = str(c.get("name", ""))
            phone = str(c.get("phone", ""))
            name_norm = _normalize_vn(name)
            if q_norm and (q_norm in name_norm or q_lower in phone):
                matches.append(c)

        if not matches:
            suggestions = [
                f"{i}. **{c.get('name', 'Khách hàng')}** ({c.get('phone', 'N/A')})"
                for i, c in enumerate(customers[:10], 1)
            ]
            return None, (
                f"⚠️ Không tìm thấy khách hàng nào khớp với tên hoặc SĐT `{query}`.\n\n"
                f"📋 **Danh sách khách hàng hiện có của bạn:**\n"
                + "\n".join(suggestions)
            )

        if len(matches) > 1:
            exact = [c for c in matches if _normalize_vn(str(c.get("name", ""))) == q_norm]
            if len(exact) == 1:
                return exact[0], None
            candidates = [
                f"- **{c.get('name')}** (SĐT: `{c.get('phone', 'N/A')}`, ID: `{c.get('id')}`)"
                for c in matches
            ]
            return None, (
                f"⚠️ Tìm thấy **{len(matches)} khách hàng** khớp với `{query}`. "
                f"Vui lòng chỉ định rõ hơn họ tên hoặc số điện thoại:\n"
                + "\n".join(candidates)
            )

        return matches[0], None

    async def _checkin(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Log daily check-in with strict validation guardrails."""
        usage_help = (
            "⚠️ **Thiếu thông tin check-in!**\n\n"
            "👉 **Cách dùng:**\n"
            "`/checkin <tên_khách> [ngày=YYYY-MM-DD] nuoc=<cốc> bua=<bữa> tap=<phút> baihoc=<1/0>`\n\n"
            "💡 **Ví dụ:**\n"
            "`/checkin Lan nuoc=8 bua=3 tap=30 baihoc=1`\n\n"
            "📌 **Quy ước chỉ số:**\n"
            "- `nuoc`: Số cốc nước (1 cốc = 250ml. Ví dụ `nuoc=8` hoặc `nuoc=2L`)\n"
            "- `bua`: Số bữa ăn lành mạnh hợp lệ (ví dụ `bua=3`)\n"
            "- `tap`: Số phút tập luyện/vận động (ví dụ `tap=30` hoặc `tap=45p`)\n"
            "- `baihoc`: Hoàn thành bài học dinh dưỡng (1: Đã học, 0: Chưa học)\n"
            "- `ngay`: Ngày check-in YYYY-MM-DD (mặc định hôm nay)"
        )
        if not args:
            return PartnerCommandResult(usage_help)

        cust_tokens: list[str] = []
        metric_tokens: list[str] = []
        for token in args:
            if "=" in token:
                metric_tokens.append(token)
            elif not metric_tokens:
                cust_tokens.append(token)
            else:
                metric_tokens.append(token)

        cust_query = " ".join(cust_tokens).strip()
        if not cust_query:
            return PartnerCommandResult(
                "⚠️ **Vui lòng chỉ định tên khách hàng cần check-in!**\n\n" + usage_help
            )

        if not metric_tokens:
            return PartnerCommandResult(
                "⚠️ **Thiếu thông tin chỉ số check-in!**\n\n"
                "Bạn cần cung cấp ít nhất một chỉ số sức khỏe để ghi nhận (nước, bữa ăn, hoặc thời gian vận động).\n\n"
                "👉 **Cách dùng:** `/checkin <tên_khách> nuoc=<số_cốc> bua=<số_bữa> tap=<số_phút> baihoc=<1/0>`\n"
                "💡 *Ví dụ:* `/checkin Lan nuoc=8 bua=3 tap=30 baihoc=1`"
            )

        from datetime import date
        checkin_date = date.today().isoformat()
        water_cups: int | None = None
        meals_logged: int | None = None
        exercise_mins: int | None = None
        lesson_completed: int | None = None

        for token in metric_tokens:
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            k = _normalize_vn(k).strip()
            v = v.strip().lower()

            if k in {"nuoc", "water"}:
                if v.endswith("l") or v.endswith("lit") or v.endswith("lít"):
                    num_part = v.rstrip("litlít ")
                    try:
                        liters = float(num_part)
                        if liters < 0 or liters > 10:
                            raise ValueError()
                        water_cups = int(round(liters * 4))
                    except ValueError:
                        return PartnerCommandResult(
                            f"⚠️ Giá trị lượng nước `{v}` không hợp lệ. Vui lòng nhập số lít (ví dụ `nuoc=2L`) hoặc số cốc (ví dụ `nuoc=8`)."
                        )
                else:
                    v_clean = v.replace("coc", "").replace("cốc", "").strip()
                    try:
                        water_cups = int(v_clean)
                        if water_cups < 0 or water_cups > 40:
                            raise ValueError()
                    except ValueError:
                        return PartnerCommandResult(
                            f"⚠️ Giá trị số cốc nước `{v}` không hợp lệ (phải từ 0 đến 40 cốc)."
                        )
            elif k in {"bua", "meal", "meals"}:
                try:
                    meals_logged = int(v)
                    if meals_logged < 0 or meals_logged > 10:
                        raise ValueError()
                except ValueError:
                    return PartnerCommandResult(
                        f"⚠️ Giá trị số bữa ăn `{v}` không hợp lệ (phải từ 0 đến 10 bữa)."
                    )
            elif k in {"tap", "ex", "exercise", "phut"}:
                v_clean = v.replace("phut", "").replace("phút", "").replace("p", "").replace("m", "").replace("min", "").strip()
                try:
                    exercise_mins = int(v_clean)
                    if exercise_mins < 0 or exercise_mins > 480:
                        raise ValueError()
                except ValueError:
                    return PartnerCommandResult(
                        f"⚠️ Thời gian vận động `{v}` không hợp lệ (phải từ 0 đến 480 phút)."
                    )
            elif k in {"baihoc", "lesson", "bai"}:
                try:
                    lesson_completed = int(v)
                    if lesson_completed not in {0, 1}:
                        raise ValueError()
                except ValueError:
                    return PartnerCommandResult(
                        f"⚠️ Chỉ số bài học `{v}` không hợp lệ (vui lòng chọn 1: Hoàn thành, 0: Chưa)."
                    )
            elif k in {"ngay", "date"}:
                try:
                    from datetime import datetime
                    datetime.strptime(v, "%Y-%m-%d")
                    checkin_date = v
                except ValueError:
                    return PartnerCommandResult(
                        f"⚠️ Ngày check-in `{v}` không đúng định dạng YYYY-MM-DD (ví dụ: `2026-09-25`)."
                    )

        if water_cups is None and meals_logged is None and exercise_mins is None and lesson_completed is None:
            return PartnerCommandResult(
                "⚠️ **Không nhận diện được chỉ số nào hợp lệ!**\n\n"
                "Vui lòng sử dụng các từ khóa: `nuoc=...`, `bua=...`, `tap=...`, `baihoc=...`"
            )

        customer, err = await self._resolve_customer(msg, cust_query)
        if err or not customer:
            return PartnerCommandResult(err or "Không tìm thấy khách hàng.")

        payload: dict[str, Any] = {
            "customerId": customer["id"],
            "date": checkin_date,
        }
        if water_cups is not None:
            payload["waterCups"] = water_cups
        if meals_logged is not None:
            payload["mealsLogged"] = meals_logged
        if exercise_mins is not None:
            payload["exerciseMinutes"] = exercise_mins
        if lesson_completed is not None:
            payload["lessonCompleted"] = lesson_completed

        ok, res = await self._call_crm_tool(msg, "customer_log_checkin", payload)
        if not ok:
            return PartnerCommandResult(str(res))

        data = res if isinstance(res, dict) else {}
        total_score = data.get("totalScore") or data.get("total_score") or 0.0

        c_name = customer.get("name") or "Khách hàng"
        liters_calc = round(water_cups * 0.25, 2) if water_cups is not None else None
        lines = [
            f"✅ **ĐÃ GHI NHẬN CHECK-IN THÀNH CÔNG!**",
            f"👤 Khách hàng: **{c_name}** | 📅 Ngày: `{checkin_date}`\n",
            "📊 **Các chỉ số ghi nhận:**",
        ]
        if water_cups is not None:
            lines.append(f"- 💧 Lượng nước: **{water_cups} cốc** (~{liters_calc}L)")
        if meals_logged is not None:
            lines.append(f"- 🥗 Bữa ăn dinh dưỡng: **{meals_logged} bữa**")
        if exercise_mins is not None:
            lines.append(f"- 🏃 Vận động: **{exercise_mins} phút**")
        if lesson_completed is not None:
            lesson_status = "Đã hoàn thành ✅" if lesson_completed == 1 else "Chưa học ⭕"
            lines.append(f"- 📖 Bài học trong ngày: **{lesson_status}**")

        lines.extend([
            f"\n🎯 **Điểm Bioclock ngày:** **{total_score}/100** ⭐",
            "💡 *Gợi ý Coach: Đừng quên nhắn tin khen ngợi sự kỷ luật của hội viên để duy trì động lực!*",
        ])
        return PartnerCommandResult("\n".join(lines))

    async def _meal(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """View meal suggestions and magic calories with customer validation."""
        if not args:
            return PartnerCommandResult(
                "⚠️ **Vui lòng chỉ định tên khách hàng cần xem thực đơn!**\n\n"
                "👉 **Cách dùng:** `/meal <tên_khách_hàng>` hoặc `/thucdon <tên_khách_hàng>`\n"
                "💡 **Ví dụ:** `/thucdon Lan`"
            )

        cust_query = " ".join(args).strip()
        customer, err = await self._resolve_customer(msg, cust_query)
        if err or not customer:
            return PartnerCommandResult(err or "Không tìm thấy khách hàng.")

        ok, profile = await self._call_crm_tool(msg, "customer_get_profile", {"id": customer["id"]})
        if not ok:
            return PartnerCommandResult(str(profile))

        prof = profile if isinstance(profile, dict) else {}
        name = prof.get("name") or customer.get("name") or "Khách hàng"
        prog = prof.get("program") or customer.get("program") or "co_nuoc_mo"
        tier = prof.get("packageTier") or customer.get("packageTier") or "basic"

        prog_titles = {
            "co_nuoc_mo": "Giảm mỡ tăng cơ (Cơ – Nước – Mỡ)",
            "dinh_duong_te_bao": "Tăng cân & Phục hồi tế bào",
            "bua_an_lanh_manh": "Bữa ăn lành mạnh & Tối ưu",
        }
        prog_name = prog_titles.get(prog, prog)

        magic_cal = prof.get("magicCalories") or customer.get("magicCalories")
        water_target = prof.get("targetWaterLiters") or customer.get("targetWaterLiters")

        # If magicCalories is not set in CRM, compute strictly using the Coach Training Standard (calorie.engine.ts)
        if not magic_cal:
            from datetime import date, datetime
            age = 30
            b_str = prof.get("birthDate") or customer.get("birthDate") or customer.get("birth_date")
            if b_str:
                try:
                    b_date = datetime.strptime(str(b_str)[:10], "%Y-%m-%d").date()
                    age = max(15, date.today().year - b_date.year)
                except Exception:
                    pass

            gender = str(prof.get("gender") or customer.get("gender") or "female").lower()
            weight = float(prof.get("targetWeightKg") or customer.get("targetWeightKg") or 60.0)
            height = float(prof.get("heightCm") or customer.get("heightCm") or (160.0 if gender == "female" else 170.0))

            # 1. RMR (Mifflin-St Jeor standard)
            if gender == "female":
                rmr = 10 * weight + 6.25 * height - 5 * age - 161
            else:
                rmr = 10 * weight + 6.25 * height - 5 * age + 5
            rmr = max(1000.0, rmr)

            # 2. AMR (25% female, 30% male)
            amr = rmr * 0.25 if gender == "female" else rmr * 0.30

            # 3. Exercise (30 mins target)
            ex_cal = 0.08 * weight * 30

            # 4. TMR
            tmr = max(1200.0, rmr + amr + ex_cal)

            # 5. Magic calories adjustment by goal & age (Coach clinical protocol)
            if prog == "co_nuoc_mo":
                adj = -300 if age >= 40 else -500
            elif prog == "dinh_duong_te_bao":
                adj = 300 if age >= 40 else 500
            else:
                adj = 0

            magic_cal = int(round(max(1000.0, tmr + adj)))

        if not water_target:
            weight = float(prof.get("targetWeightKg") or customer.get("targetWeightKg") or 60.0)
            if prog == "co_nuoc_mo":
                water_target = round((weight / 10.0) * 0.65, 1)
            else:
                water_target = round((weight / 10.0) * 0.4, 1)

        lines = [
            f"📋 **GỢI Ý THỰC ĐƠN DINH DƯỠNG: {name}**",
            f"🎯 Chương trình: **{prog_name}** (Gói: `{tier}`)\n",
            f"🔥 **Con số Calo kỳ diệu:** **{magic_cal:,} kcal/ngày**",
            f"💧 **Nước mục tiêu:** **{water_target} L/ngày** (~{int(water_target * 4)} cốc)\n",
            "⚖️ **Tỷ lệ đa lượng khuyến nghị (Macro):**",
            "- 🥩 **Đạm (Protein):** 30% (~95g đạm sạch)",
            "- 🍚 **Đường bột tốt (Carb):** 45% (Chỉ số GI thấp: khoai lang, yến mạch)",
            "- 🥑 **Chất béo tốt (Fat):** 25% (Omega-3, dầu olive, hạt)\n",
            "🕒 **Khung phân bổ 5 bữa ăn trong ngày:**",
            "- **07:00 (Sáng):** 2 muỗng F1 + 1 muỗng Protein PPP + 300ml nước ấm (~200 kcal)",
            "- **09:30 (Phụ sáng):** 1 tách Trà thảo mộc + 1 quả táo hoặc 1 hộp sữa chua Hy Lạp (~80 kcal)",
            "- **12:00 (Trưa):** 150g ức gà/cá hấp + 1 đĩa rau củ luộc + 1/2 củ khoai lang (~450 kcal)",
            "- **15:30 (Phụ chiều):** Trà thảo mộc thanh lọc + 1 lòng trắng trứng luộc (~50 kcal)",
            "- **18:30 (Tối):** 2 muỗng F1 + rau xanh luộc hoặc salad trộn giấm táo (~250 kcal)",
            "\n💡 *Gợi ý Coach: Nhắc nhở hội viên uống 1 ly nước ấm ngay trước mỗi bữa ăn 15-30 phút.*",
        ]
        return PartnerCommandResult("\n".join(lines))

    async def _report(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """View customer progress, streak, and metrics with customer validation."""
        if not args:
            return PartnerCommandResult(
                "⚠️ **Vui lòng chỉ định tên khách hàng cần xem báo cáo tiến độ!**\n\n"
                "👉 **Cách dùng:** `/report <tên_khách_hàng>` hoặc `/baocao <tên_khách_hàng>`\n"
                "💡 **Ví dụ:** `/report Lan`"
            )

        cust_query = " ".join(args).strip()
        customer, err = await self._resolve_customer(msg, cust_query)
        if err or not customer:
            return PartnerCommandResult(err or "Không tìm thấy khách hàng.")

        ok, progress = await self._call_crm_tool(msg, "customer_get_progress", {"customerId": customer["id"]})
        if not ok:
            return PartnerCommandResult(str(progress))

        prog = progress if isinstance(progress, dict) else {}
        name = prog.get("customerName") or customer.get("name") or "Khách hàng"
        total_ci = prog.get("totalCheckins", 0)
        streak = prog.get("checkinStreak", 0)
        avg_score = round(prog.get("averageScore", 0.0), 1)

        lines = [
            f"📊 **BÁO CÁO TIẾN ĐỘ & TRẢI NGHIỆM: {name}**",
            f"📅 Cập nhật đến ngày hôm nay\n",
            "🏃 **Kỷ luật Check-in:**",
            f"- Tổng số ngày check-in: **{total_ci} ngày**",
            f"- Chuỗi check-in liên tục (Streak): **{streak} ngày** 🔥",
            f"- Điểm kỷ luật Bioclock trung bình: **{avg_score}/100** ⭐\n",
        ]

        wt = prog.get("weightTrend")
        if wt and isinstance(wt, dict):
            init_kg = wt.get("initialKg", 0)
            curr_kg = wt.get("currentKg", 0)
            diff_kg = wt.get("diffKg", 0)
            sign = "+" if diff_kg > 0 else ""
            lines.extend([
                "⚖️ **Biến thiên cân nặng:**",
                f"- Cân nặng ban đầu: `{init_kg} kg`",
                f"- Cân nặng hiện tại: `{curr_kg} kg`",
                f"- Mức thay đổi: **{sign}{diff_kg} kg** 🎯\n",
            ])

        lines.extend([
            "💡 **Đánh giá & Lời khuyên của Coach:**",
            "- Hội viên duy trì nhịp độ rất tốt. Tiếp tục bám sát thực đơn và nhắc hội viên ngủ trước 23:00.",
        ])
        return PartnerCommandResult("\n".join(lines))

    async def _script(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Generate targeted coaching talking points with customer and topic validation."""
        usage_help = (
            "⚠️ **Thiếu thông tin tạo kịch bản chăm sóc!**\n\n"
            "👉 **Cách dùng:** `/script <tên_khách> <chủ_đề_hoặc_ngày>`\n\n"
            "💡 **Ví dụ:**\n"
            "- `/script Lan ngay_3` (Chăm sóc ngày thứ 3: Hiện tượng thải độc)\n"
            "- `/script Lan ngay_7` (Chăm sóc ngày thứ 7: Củng cố thói quen)\n"
            "- `/script Lan chan_an_uc_ga` (Gợi ý đổi món khi ngán gà)\n"
            "- `/script Lan che_gia_cao` (Xử lý phản đối về giá)"
        )
        if not args:
            return PartnerCommandResult(usage_help)

        if len(args) < 2:
            return PartnerCommandResult(
                f"⚠️ **Vui lòng cung cấp chủ đề hoặc ngày chăm sóc cho khách hàng `{args[0]}`!**\n\n"
                + usage_help
            )

        cust_query = args[0].strip()
        topic = " ".join(args[1:]).strip()

        customer, err = await self._resolve_customer(msg, cust_query)
        if err or not customer:
            return PartnerCommandResult(err or "Không tìm thấy khách hàng.")

        c_name = customer.get("name") or "Khách hàng"
        topic_norm = _normalize_vn(topic)

        # Retrieve relevant objection handling or lesson if applicable
        if any(w in topic_norm for w in ["gia", "dat", "tien", "suy nghi", "nguoi nha"]):
            await self._call_crm_tool(msg, "skill_get", {"name": "objection-handling"})

        if "3" in topic_norm or "thai doc" in topic_norm or "met" in topic_norm:
            title = "Chăm sóc Ngày 3: Hiện tượng đào thải độc tố & Thích nghi"
            p1 = "Hỏi thăm cảm nhận cơ thể (có thấy hơi cồn cào, buồn ngủ hoặc chóng mặt nhẹ không). Lắng nghe trọn vẹn và chúc mừng khách hàng."
            p2 = "Giải thích khoa học: Khi cắt giảm calo rỗng và đưa trà thảo mộc vào, cơ thể đang bắt đầu cơ chế dọn rác tế bào và đốt mỡ thừa."
            p3 = "Hành động: Nhắc uống từng ngụm nước ấm nhỏ đều đặn từ giờ đến 16:00, không nhịn đói bữa phụ, duy trì đủ bữa F1."
        elif "7" in topic_norm or "quen" in topic_norm or "mot tuan" in topic_norm:
            title = "Chăm sóc Ngày 7: Củng cố thói quen & Đo quét Tanita lần 1"
            p1 = "Chúc mừng cột mốc 7 ngày đầu tiên! Ghi nhận sự nỗ lực và khen ngợi chuỗi kỷ luật check-in của khách."
            p2 = "Nhắc nhở ý nghĩa của 7 ngày: Dạ dày bắt đầu co lại về kích thước tự nhiên, vị giác nhạy hơn và giảm cảm giác thèm ngọt."
            p3 = "Hành động: Đặt lịch hẹn qua CLB quét chỉ số Tanita để xem lượng mỡ giảm và lượng nước cơ thể tăng."
        elif "uc ga" in topic_norm or "mon" in topic_norm or "ngan" in topic_norm or "doi mon" in topic_norm:
            title = "Tư vấn Đổi món tương đương khi ngán Ức gà"
            p1 = "Đồng cảm: 'Ăn ức gà liên tục 1 tuần ai cũng dễ bị ngán, em sẽ hướng dẫn chị đổi sang các nguồn đạm tương đương ngay nhé!'"
            p2 = "Giải thích: 150g ức gà = 160g cá nạc (cá basa, cá hồi phi lê, tôm) = 200g đậu hũ non + 2 lòng trắng trứng luộc."
            p3 = "Hành động: Chế biến áp chảo ít dầu hoặc hấp sả, ướp tiêu chanh thay vì luộc nhạt."
        elif "gia" in topic_norm or "dat" in topic_norm or "tien" in topic_norm:
            title = "Xử lý phản đối về Giá & Chi phí gói dinh dưỡng"
            p1 = "Đồng cảm: 'Em hiểu, khi mới nghe qua tổng chi phí gói thì ai cũng thấy đây là một khoản cần cân nhắc.'"
            p2 = "Chia nhỏ bài toán chi phí: 'Thực tế gói này đã thay thế hoàn toàn bữa sáng và bữa phụ của chị, mỗi bữa chỉ tương đương một bát phở (~50k) nhưng mang lại 21 vitamin khoáng chất.'"
            p3 = "Cam kết đồng hành: 'Quan trọng nhất là sự đồng hành 1-1 của em hàng ngày để đảm bảo chị đạt kết quả giảm mỡ rõ ràng.'"
        else:
            title = f"Kịch bản chăm sóc cá nhân hóa: {topic}"
            p1 = f"Kết nối & Đặt câu hỏi mở: Hỏi thăm tình hình ăn uống và sinh hoạt của {c_name} trong 24h qua."
            p2 = "Chia sẻ kiến thức: Giải thích mối liên hệ giữa việc uống đủ nước, đạm sạch và mục tiêu sức khỏe của hội viên."
            p3 = "Kêu gọi hành động: Đưa ra 1 việc cụ thể hội viên cần hoàn thành trước buổi tối hôm nay."

        lines = [
            f"🗣️ **TALKING POINT CHĂM SÓC: {c_name}**",
            f"📌 Chủ đề: **{title}**\n",
            f"1. **Bước 1 (Đồng cảm & Khơi gợi):** {p1}",
            f"2. **Bước 2 (Khoa học & Đơn giản):** {p2}",
            f"3. **Bước 3 (Hành động cụ thể):** {p3}",
            "\n💡 *Gợi ý Coach: Giữ giọng điệu ấm áp, tích cực và luôn kết thúc bằng lời động viên.*",
        ]
        return PartnerCommandResult("\n".join(lines))

    def _dispatch_conversational(self, msg: InboundMessage) -> Any:
        text = msg.content.strip().lower()
        if not text or len(text) < 3:
            return None

        # Checkin conversational
        if text.startswith("checkin ") or text.startswith("check in ") or text.startswith("/checkin"):
            parts = text.split()
            sub_args = [p for p in parts if p not in {"checkin", "check", "in", "/checkin", "cho"}]
            return self._checkin(msg, sub_args)

        bday_keywords = ["sinh nhật", "sinh nhat", "ngày sinh", "ngay sinh"]
        if any(kw in text for kw in bday_keywords):
            return self._birthdays(msg, [])

        cust_keywords = [
            "thống kê khách hàng",
            "thong ke khach hang",
            "thống kê số lượng khách hàng",
            "số lượng khách hàng",
            "so luong khach hang",
            "danh sách khách hàng",
            "danh sach khach hang",
            "bao nhiêu khách hàng",
            "khách hàng hiện tại",
            "khach hang hien tai",
            "tổng số khách hàng",
            "tong so khach hang",
        ]
        if any(kw in text for kw in cust_keywords) and not ("nhiệm vụ" in text or "công việc" in text):
            return self._customers(msg, [])

        task_keywords = [
            "nhiệm vụ hôm nay",
            "nhiem vu hom nay",
            "công việc hôm nay",
            "cong viec hom nay",
            "việc cần làm",
            "danh sách nhiệm vụ",
            "task hôm nay",
        ]
        if any(kw in text for kw in task_keywords):
            return self._tasks(msg, [])

        # Meal / thuc don conversational
        if any(kw in text for kw in ["thực đơn", "thuc don", "bữa ăn"]) and not ("thống kê" in text or "sinh nhật" in text):
            cleaned = text
            for kw in ["thực đơn", "thuc don", "bữa ăn", "cho", "của", "chị", "anh", "em", "hội viên", "khách hàng"]:
                cleaned = cleaned.replace(kw, " ")
            cust_name = cleaned.strip()
            if cust_name:
                return self._meal(msg, [cust_name])

        # Progress / report conversational
        if any(kw in text for kw in ["tiến độ", "tien do", "báo cáo", "bao cao", "kết quả", "ket qua"]) and not ("thống kê" in text or "sinh nhật" in text or "nhiệm vụ" in text):
            cleaned = text
            for kw in ["tiến độ", "tien do", "báo cáo", "bao cao", "kết quả", "ket qua", "cho", "của", "chị", "anh", "em"]:
                cleaned = cleaned.replace(kw, " ")
            cust_name = cleaned.strip()
            if cust_name:
                return self._report(msg, [cust_name])

        # Script / talking point conversational
        if any(kw in text for kw in ["kịch bản", "kich ban", "talking point", "bài học", "bai hoc"]):
            cleaned = text
            for kw in ["kịch bản", "kich ban", "talking point", "bài học", "bai hoc", "cho", "chăm sóc"]:
                cleaned = cleaned.replace(kw, " ")
            parts = cleaned.strip().split()
            if len(parts) >= 2:
                return self._script(msg, parts)

        return None

    def _link(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        """Claim a link code, so this chat account speaks as its owner from now on."""
        from deeptutor.services.partners.interaction import actor_for_account
        from deeptutor.services.partners.links import redeem_link_code

        if msg.channel == "web":
            return PartnerCommandResult("You're already signed in here — nothing to link.")
        if (msg.metadata or {}).get("is_group"):
            return PartnerCommandResult(
                "Send /link in a direct message instead — group chats stay shared, "
                "and a code posted in one would be visible to everyone."
            )
        if not args:
            return PartnerCommandResult(
                "Usage: /link <code>. Open this partner in DeepTutor and choose "
                "“Link this chat account” to get a code."
            )
        user_id = redeem_link_code(
            self.partner_id, args[0], channel=msg.channel, sender_id=msg.sender_id
        )
        if not user_id:
            return PartnerCommandResult(
                "That code is not valid — it may have expired or already been used. "
                "Generate a fresh one in DeepTutor and try again."
            )
        actor = actor_for_account(user_id)
        if actor is None:
            return PartnerCommandResult("That code belongs to an account that no longer exists.")
        return PartnerCommandResult(
            f"Linked — I'll talk to you as {actor.username} from now on. "
            "This conversation is private to your account, and I can reach your "
            "library and notes here just like in the app."
        )

    def _new(self, msg: InboundMessage) -> PartnerCommandResult:
        archived = self.store.archive(msg.session_key)
        if archived:
            return PartnerCommandResult(
                "Started a new conversation.\n"
                f"Archived {archived['message_count']} message(s) as `{archived['session_key']}`."
            )
        return PartnerCommandResult("Started a new conversation. No prior messages to archive.")

    def _branch(self, msg: InboundMessage) -> PartnerCommandResult:
        # Branching to a *copy* needs a new session key, which only the web app
        # mints; on IM there is one session per chat, so degrade to /new.
        archived = self.store.archive(msg.session_key)
        if archived:
            return PartnerCommandResult(
                f"Archived this conversation as `{archived['session_key']}` and started fresh. "
                "To keep the full history in a new branch, use the web app."
            )
        return PartnerCommandResult("Nothing to branch yet.")

    def _sessions(self) -> PartnerCommandResult:
        sessions = self.store.list_sessions()
        if not sessions:
            return PartnerCommandResult("No conversations yet.")
        lines = ["Conversations:"]
        for session in sessions[:30]:
            flag = " (archived)" if session.get("archived") else ""
            title = str(session.get("title") or "").strip() or "(untitled)"
            lines.append(
                f"- `{session['session_key']}`{flag} — {title} · {session['message_count']} msg"
            )
        lines.append("\nUse /resume <session ID> or /delete <session ID>.")
        return PartnerCommandResult("\n".join(lines))

    def _resume(self, args: list[str]) -> PartnerCommandResult:
        if not args:
            return PartnerCommandResult("Usage: /resume <session ID>")
        key = args[0]
        self.store.set_archived(key, False)
        return PartnerCommandResult(
            f"Conversation `{key}` is active again. In the web app it reopens automatically."
        )

    def _delete(self, args: list[str]) -> PartnerCommandResult:
        if not args:
            return PartnerCommandResult("Usage: /delete <session ID>")
        key = args[0]
        removed = self.store.delete_session(key)
        return PartnerCommandResult(
            f"Deleted conversation `{key}`." if removed else f"No conversation `{key}` found."
        )

    def _status(self, msg: InboundMessage) -> PartnerCommandResult:
        selection = getattr(self.config, "llm_selection", None) or {}
        model = (
            (selection.get("model_id") if isinstance(selection, dict) else None)
            or getattr(self.config, "model", None)
            or "default"
        )
        tools = self._current_tools()
        messages = self.store.messages(msg.session_key, limit=10_000)
        lines = [
            "Partner status:",
            f"- Partner: {getattr(self.config, 'name', self.partner_id)} (`{self.partner_id}`)",
            f"- Channel: {msg.channel}",
            f"- Session: `{msg.session_key}`",
            f"- Model: `{model}`",
            f"- Messages in current conversation: {len(messages)}",
            f"- Tools: {', '.join(f'`{name}`' for name in tools) if tools else '(none)'}",
        ]
        return PartnerCommandResult("\n".join(lines))

    def _history(self, msg: InboundMessage, args: list[str]) -> PartnerCommandResult:
        count = 10
        if args:
            try:
                count = max(1, min(int(args[0]), 50))
            except ValueError:
                return PartnerCommandResult("Usage: /history [count]")
        records = self.store.messages(msg.session_key, limit=count)
        visible = [self._format_message(record) for record in records]
        visible = [line for line in visible if line]
        if not visible:
            return PartnerCommandResult("No conversation history yet.")
        return PartnerCommandResult(f"Last {len(visible)} message(s):\n" + "\n".join(visible))

    def _tool(self, args: list[str]) -> PartnerCommandResult:
        available = default_optional_tools()
        current = self._current_tools()
        if not args:
            return PartnerCommandResult(self._format_tools(current, available))

        action = args[0].lower()
        if action == "reset":
            setattr(self.config, "enabled_tools", None)
            self._persist_config()
            return PartnerCommandResult(self._format_tools(self._current_tools(), available))

        if action not in {"on", "off"} or len(args) < 2:
            return PartnerCommandResult("Usage: /tool [on|off <name>|reset]")

        name = args[1]
        if name not in available:
            return PartnerCommandResult(
                f"Unknown tool `{name}`.\nAvailable: {', '.join(f'`{tool}`' for tool in available)}"
            )

        next_tools = list(current)
        if action == "on" and name not in next_tools:
            next_tools.append(name)
        elif action == "off" and name in next_tools:
            next_tools.remove(name)
        setattr(self.config, "enabled_tools", next_tools)
        self._persist_config()
        return PartnerCommandResult(self._format_tools(next_tools, available))

    def _current_tools(self) -> list[str]:
        configured = getattr(self.config, "enabled_tools", None)
        if configured is None:
            return default_optional_tools()
        available = set(default_optional_tools())
        return [str(name) for name in configured if str(name) in available]

    def _persist_config(self) -> None:
        if self.save_config is not None:
            self.save_config(self.partner_id, self.config)

    @staticmethod
    def _format_message(record: dict[str, Any]) -> str:
        role = str(record.get("role") or "")
        if role not in {"user", "assistant"}:
            return ""
        content = str(record.get("content") or "").strip()
        if not content:
            return ""
        if len(content) > 200:
            content = content[:199] + "..."
        label = "You" if role == "user" else "Partner"
        return f"{label}: {content}"

    @staticmethod
    def _format_tools(current: list[str], available: list[str]) -> str:
        return "\n".join(
            [
                "Tools:",
                f"- Enabled: {', '.join(f'`{name}`' for name in current) if current else '(none)'}",
                f"- Available: {', '.join(f'`{name}`' for name in available) if available else '(none)'}",
            ]
        )


__all__ = [
    "PartnerCommandHandler",
    "PartnerCommandResult",
    "PartnerCommandSpec",
    "build_partner_help_text",
    "looks_like_partner_command",
    "partner_command_palette",
]
