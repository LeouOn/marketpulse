"""
Real-Time Alert System

Multi-channel notifications for trading signals:
- Desktop notifications
- Telegram bot
- Email alerts
- Webhook notifications (for mobile apps)
- Console logging

Priority levels: low, medium, high, critical
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import asyncio
import os
from loguru import logger


class AlertPriority(Enum):
    """Alert priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Available alert channels"""
    DESKTOP = "desktop"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    CONSOLE = "console"


@dataclass
class Alert:
    """Alert message"""
    title: str
    message: str
    priority: AlertPriority
    timestamp: datetime
    data: Optional[Dict[str, Any]] = None


class DesktopNotifier:
    """Desktop notifications (using plyer or similar)"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

        if enabled:
            try:
                # Try to import notification library
                import plyer
                self.plyer = plyer
                self.available = True
                logger.info("Desktop notifications enabled")
            except ImportError:
                logger.warning("plyer not installed - desktop notifications disabled")
                self.available = False
        else:
            self.available = False

    async def send(self, alert: Alert) -> bool:
        """Send desktop notification"""
        if not self.available or not self.enabled:
            return False

        try:
            self.plyer.notification.notify(
                title=alert.title,
                message=alert.message,
                app_name='MarketPulse',
                timeout=10 if alert.priority != AlertPriority.CRITICAL else 30
            )
            logger.debug(f"Desktop notification sent: {alert.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send desktop notification: {e}")
            return False


class TelegramNotifier:
    """Telegram bot notifications"""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True
    ):
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = enabled and self.token and self.chat_id

        if self.enabled:
            logger.info("Telegram notifications enabled")
        else:
            logger.info("Telegram notifications disabled (no token/chat_id)")

    async def send(self, alert: Alert) -> bool:
        """Send Telegram message"""
        if not self.enabled:
            return False

        try:
            import aiohttp

            url = f"https://api.telegram.org/bot{self.token}/sendMessage"

            # Format message with emoji based on priority
            emoji = self._get_emoji(alert.priority)
            formatted_message = f"{emoji} *{alert.title}*\n\n{alert.message}"

            payload = {
                'chat_id': self.chat_id,
                'text': formatted_message,
                'parse_mode': 'Markdown'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug(f"Telegram message sent: {alert.title}")
                        return True
                    else:
                        logger.error(f"Telegram send failed: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def _get_emoji(self, priority: AlertPriority) -> str:
        """Get emoji for priority level"""
        emoji_map = {
            AlertPriority.LOW: "ℹ️",
            AlertPriority.MEDIUM: "📊",
            AlertPriority.HIGH: "🎯",
            AlertPriority.CRITICAL: "🚨"
        }
        return emoji_map.get(priority, "📢")


class EmailNotifier:
    """Email notifications"""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        enabled: bool = True
    ):
        self.smtp_host = smtp_host or os.getenv('SMTP_HOST')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.username = username or os.getenv('SMTP_USERNAME')
        self.password = password or os.getenv('SMTP_PASSWORD')
        self.from_email = from_email or os.getenv('EMAIL_FROM')
        self.to_email = to_email or os.getenv('EMAIL_TO')

        self.enabled = enabled and all([
            self.smtp_host, self.username, self.password,
            self.from_email, self.to_email
        ])

        if self.enabled:
            logger.info("Email notifications enabled")
        else:
            logger.info("Email notifications disabled (missing SMTP config)")

    async def send(self, alert: Alert) -> bool:
        """Send email notification"""
        if not self.enabled:
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            msg['Subject'] = f"[{alert.priority.value.upper()}] {alert.title}"

            body = f"""
{alert.message}

---
Priority: {alert.priority.value}
Timestamp: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

MarketPulse Trading System
            """

            msg.attach(MIMEText(body, 'plain'))

            # Send via SMTP
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()

            logger.debug(f"Email sent: {alert.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class WebhookNotifier:
    """Webhook notifications (for custom integrations)"""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        enabled: bool = True
    ):
        self.webhook_url = webhook_url or os.getenv('WEBHOOK_URL')
        self.enabled = enabled and self.webhook_url

        if self.enabled:
            logger.info(f"Webhook notifications enabled: {self.webhook_url}")
        else:
            logger.info("Webhook notifications disabled (no URL)")

    async def send(self, alert: Alert) -> bool:
        """Send webhook notification"""
        if not self.enabled:
            return False

        try:
            import aiohttp

            payload = {
                'title': alert.title,
                'message': alert.message,
                'priority': alert.priority.value,
                'timestamp': alert.timestamp.isoformat(),
                'data': alert.data
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.debug(f"Webhook sent: {alert.title}")
                        return True
                    else:
                        logger.error(f"Webhook send failed: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False


class ConsoleNotifier:
    """Console/log notifications"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    async def send(self, alert: Alert) -> bool:
        """Log to console"""
        if not self.enabled:
            return False

        priority_symbols = {
            AlertPriority.LOW: "ℹ️",
            AlertPriority.MEDIUM: "📊",
            AlertPriority.HIGH: "🎯",
            AlertPriority.CRITICAL: "🚨"
        }

        symbol = priority_symbols.get(alert.priority, "📢")
        logger.info(f"{symbol} [{alert.priority.value.upper()}] {alert.title}: {alert.message}")
        return True


class AlertManager:
    """
    Multi-channel alert manager

    Manages notifications across multiple channels with priority routing.
    """

    def __init__(
        self,
        enabled_channels: Optional[List[AlertChannel]] = None,
        min_priority: AlertPriority = AlertPriority.LOW
    ):
        """
        Initialize alert manager

        Args:
            enabled_channels: List of enabled channels (None = all available)
            min_priority: Minimum priority to send alerts
        """
        self.min_priority = min_priority

        # Initialize notifiers
        self.notifiers = {
            AlertChannel.DESKTOP: DesktopNotifier(),
            AlertChannel.TELEGRAM: TelegramNotifier(),
            AlertChannel.EMAIL: EmailNotifier(),
            AlertChannel.WEBHOOK: WebhookNotifier(),
            AlertChannel.CONSOLE: ConsoleNotifier()
        }

        # Filter by enabled channels
        if enabled_channels:
            self.notifiers = {
                ch: notif for ch, notif in self.notifiers.items()
                if ch in enabled_channels
            }

        active_channels = [
            ch.value for ch, notif in self.notifiers.items()
            if getattr(notif, 'enabled', True) and getattr(notif, 'available', True)
        ]

        logger.info(f"Alert Manager initialized. Active channels: {active_channels}")

    async def send_alert(
        self,
        title: str,
        message: str,
        priority: AlertPriority = AlertPriority.MEDIUM,
        data: Optional[Dict[str, Any]] = None,
        channels: Optional[List[AlertChannel]] = None
    ) -> Dict[AlertChannel, bool]:
        """
        Send alert to specified channels

        Args:
            title: Alert title
            message: Alert message
            priority: Alert priority
            data: Additional data (optional)
            channels: Specific channels to use (None = all)

        Returns:
            Dictionary of channel -> success status
        """
        # Check minimum priority
        if priority.value < self.min_priority.value:
            logger.debug(f"Alert skipped (below min priority): {title}")
            return {}

        alert = Alert(
            title=title,
            message=message,
            priority=priority,
            timestamp=datetime.now(),
            data=data
        )

        # Determine which channels to use
        target_notifiers = self.notifiers
        if channels:
            target_notifiers = {
                ch: notif for ch, notif in self.notifiers.items()
                if ch in channels
            }

        # Send to all channels concurrently
        results = {}
        tasks = []

        for channel, notifier in target_notifiers.items():
            tasks.append(self._send_to_channel(channel, notifier, alert))

        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for (channel, _), result in zip(target_notifiers.items(), task_results):
            if isinstance(result, Exception):
                logger.error(f"Alert send error on {channel.value}: {result}")
                results[channel] = False
            else:
                results[channel] = result

        return results

    async def _send_to_channel(
        self,
        channel: AlertChannel,
        notifier: Any,
        alert: Alert
    ) -> bool:
        """Send alert to specific channel"""
        try:
            return await notifier.send(alert)
        except Exception as e:
            logger.error(f"Error sending to {channel.value}: {e}")
            return False

    async def send_trade_signal(
        self,
        symbol: str,
        signal_type: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk: float,
        reward: float,
        confidence: float,
        reasoning: str,
        priority: AlertPriority = AlertPriority.HIGH
    ) -> Dict[AlertChannel, bool]:
        """
        Send trading signal alert

        Args:
            symbol: Trading symbol
            signal_type: "LONG" or "SHORT"
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            risk: Risk in dollars
            reward: Reward in dollars
            confidence: Signal confidence (0-100)
            reasoning: Signal reasoning
            priority: Alert priority

        Returns:
            Dictionary of channel -> success status
        """
        rr_ratio = reward / risk if risk > 0 else 0

        message = f"""
🎯 {signal_type} SIGNAL - {symbol}

Entry: {entry_price:.2f}
Stop: {stop_loss:.2f}
Target: {take_profit:.2f}

Risk: ${risk:.0f}
Reward: ${reward:.0f}
R:R: {rr_ratio:.2f}:1
Confidence: {confidence:.0f}%

{reasoning}
        """.strip()

        return await self.send_alert(
            title=f"{signal_type} Signal - {symbol}",
            message=message,
            priority=priority,
            data={
                'symbol': symbol,
                'type': signal_type,
                'entry': entry_price,
                'stop': stop_loss,
                'target': take_profit,
                'risk': risk,
                'reward': reward,
                'rr': rr_ratio,
                'confidence': confidence
            }
        )

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        priority: AlertPriority = AlertPriority.CRITICAL
    ) -> Dict[AlertChannel, bool]:
        """
        Send risk management alert

        Args:
            alert_type: Type of risk alert
            message: Alert message
            priority: Alert priority

        Returns:
            Dictionary of channel -> success status
        """
        return await self.send_alert(
            title=f"Risk Alert: {alert_type}",
            message=message,
            priority=priority
        )

    async def send_position_update(
        self,
        symbol: str,
        action: str,
        price: float,
        pnl: Optional[float] = None,
        priority: AlertPriority = AlertPriority.MEDIUM
    ) -> Dict[AlertChannel, bool]:
        """
        Send position update alert

        Args:
            symbol: Trading symbol
            action: "OPENED", "CLOSED", "STOPPED_OUT", etc.
            price: Price at action
            pnl: P&L if closing
            priority: Alert priority

        Returns:
            Dictionary of channel -> success status
        """
        message = f"Position {action}: {symbol} @ {price:.2f}"

        if pnl is not None:
            message += f"\nP&L: ${pnl:+.2f}"

        return await self.send_alert(
            title=f"Position {action}",
            message=message,
            priority=priority,
            data={
                'symbol': symbol,
                'action': action,
                'price': price,
                'pnl': pnl
            }
        )
