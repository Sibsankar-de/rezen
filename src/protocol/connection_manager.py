import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from protocol.protocol import RLP
from protocol.packet import Packet, PacketType
from protocol.serializer import TCPSerializer
from models.connection import Connection, ConnectionState
from models.device import Device

PacketHandler = Callable[
    [Connection, Packet],
    Awaitable[None],
]


class ConnectionManager:
    """TCP connection manager class for managing connections to devices."""

    def __init__(
        self,
        current_device: Device,
        port: int = RLP.DEFAULT_PORT,
    ):
        self._port = port
        self._current_device = current_device
        self._connections: dict[str, Connection] = {}
        self._handlers: set[PacketHandler] = set()
        self._running = False
        self._listener_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the connection manager."""
        if self._running:
            return

        await self._start_server()

        self._running = True

        # start listeners for all connections
        for connection in self._connections.values():
            self._start_listener(connection)

    async def stop(self) -> None:
        """Stop the connection manager."""
        if not self._running:
            return

        self._running = False

    async def connect(self, remote_device: Device) -> Connection:
        """Creates a new connection with a remote device"""
        remote_ip, remote_port = remote_device.ip, remote_device.port
        reader, writer = await asyncio.open_connection(remote_ip, remote_port)

        connection = await self._create_register_connection(
            device_id=remote_device.id,
            remote_ip=remote_ip,
            remote_port=remote_port,
            reader=reader,
            writer=writer,
        )

        # send hello packet
        await self._send_hello_packet(connection)

        return connection

    async def disconnect(self, connection_id: str) -> None:
        """Disconnect a connection"""
        connection = self._connections.get(connection_id)

        if connection is None:
            return

        connection.state = ConnectionState.DISCONNECTING

        # remove the listener task
        task = self._listener_tasks.pop(connection_id, None)

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            await self._close_writer(connection.writer)

        finally:
            connection.state = ConnectionState.DISCONNECTED
            self._connections.pop(connection_id, None)

    async def _start_server(self) -> None:
        """Starts the tcp server"""
        self._server = await asyncio.start_server(
            self._accept_connection,
            host="0.0.0.0",
            port=self._port,
        )

    async def _accept_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Creates the connection object and sends a hello packet"""
        remote_address = writer.get_extra_info("peername")

        if remote_address is None:
            writer.close()
            await writer.wait_closed()
            return

        remote_ip = remote_address[0]
        remote_port = remote_address[1]

        try:
            # Receive remote device id from hello packet
            hello_packet = await self._receive_hello_packet(reader)

            connection = await self._create_register_connection(
                device_id=hello_packet.device_id,
                remote_ip=remote_ip,
                remote_port=remote_port,
                reader=reader,
                writer=writer,
            )

            # send ack packet
            await self._ack_hello_packet(connection)

            await self._handle_packet(connection, hello_packet)

        except asyncio.TimeoutError:
            await self._close_writer(writer)

        except (
            asyncio.IncompleteReadError,
            ConnectionError,
            ValueError,
        ):
            await self._close_writer(writer)

        except Exception:
            await self._close_writer(writer)

    async def _send_hello_packet(self, connection: Connection) -> None:
        """Sends a hello packet on connection start"""
        hello_packet = Packet(
            type=PacketType.HELLO,
            device_id=self._current_device.id,
            version=RLP.VERSION,
            payload={"device_id": self._current_device.id},
        )

        await self._send(connection, hello_packet)

    async def _receive_hello_packet(self, reader: asyncio.StreamReader) -> Packet:
        """Receive hello packet and deserialize it"""
        hello_packet = await asyncio.wait_for(
            TCPSerializer.deserialize(reader), timeout=10
        )

        if hello_packet.type != PacketType.HELLO:
            ConnectionError("Invalid hello packet.")

        return hello_packet

    async def _ack_hello_packet(self, connection: Connection) -> None:
        """Send hello packet Acknowledgement to the remote device"""
        hello_ack = Packet(
            type=PacketType.HELLO_ACK,
            device_id=self._current_device.id,
            version=RLP.VERSION,
            payload={"device_id": self._current_device.id},
        )

        await self._send(connection, hello_ack)

    async def _create_register_connection(
        self,
        device_id: str,
        remote_ip: str,
        remote_port: str | int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Connection:
        """Creates a new connection object and registers it."""
        now = datetime.now()

        new_connection = Connection(
            id=f"{device_id}:{remote_ip}:{remote_port}",
            device_id=device_id,
            remote_port=remote_port,
            remote_ip=remote_ip,
            reader=reader,
            writer=writer,
            state=ConnectionState.CONNECTED,
            connected_at=now,
            last_activity_at=now,
        )

        self._connections[new_connection.id] = new_connection

        # start listener for the connection
        if self._running:
            self._start_listener(new_connection)

        return new_connection

    async def _start_listener(self, connection: Connection) -> None:
        if connection.id in self._listener_tasks:
            return

        task = asyncio.create_task(self._listen(connection))

        self._listener_tasks[connection.id] = task

    async def _listen(self, connection: Connection) -> None:
        """Continuously listens and receive packets"""
        try:
            while self._running and connection.state == ConnectionState.CONNECTED:
                packet = await TCPSerializer.deserialize(connection.reader)

                connection.last_activity_at = datetime.now()

                await self._handle_packet(connection, packet)

        except asyncio.CancelledError:
            raise

        except asyncio.IncompleteReadError:
            # Remote side closed the connection.
            pass

        except ConnectionError:
            pass

        except Exception:
            # unexpected connection errors.
            pass

        finally:
            await self._cleanup_connection(connection)

    async def _handle_packet(
        self,
        connection: Connection,
        packet: Packet,
    ) -> None:

        handlers = tuple(self._handlers)

        if not handlers:
            return

        await asyncio.gather(
            *(handler(connection, packet) for handler in handlers),
            return_exceptions=True,
        )

    async def subscribe(self, handler: PacketHandler) -> None:
        """Subscribes to a new handler"""
        self._handlers.add(handler)

    async def unsubscribe(self, handler: PacketHandler) -> None:
        """Unsubcribe a handler"""
        self._handlers.discard(handler)

    async def send(self, connection_id: str, packet: Packet) -> None:
        """Send a packet in a connection"""
        connection = self._connections.get(connection_id, None)
        if connection is None:
            raise ConnectionError(f"Connection not found: {connection_id}")

        await self._send(connection, packet)

    async def _send(self, connection: Connection, packet: Packet) -> None:
        """Send a packet in a connection"""
        if connection.state != ConnectionState.CONNECTED:
            raise ConnectionError(f"Connection is connected: {connection.id}")

        data = TCPSerializer.serialize(packet)

        connection.writer.write(data)
        await connection.writer.drain()

        connection.last_activity_at = datetime.now()

    async def _cleanup_connection(
        self,
        connection: Connection,
    ) -> None:
        """Cleanup the connection states"""
        self._listener_tasks.pop(connection.id, None)
        self._connections.pop(connection.id, None)

        connection.state = ConnectionState.DISCONNECTED

        await self._close_writer(connection.writer)

    async def _close_writer(
        self,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Safely close a writer."""
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
