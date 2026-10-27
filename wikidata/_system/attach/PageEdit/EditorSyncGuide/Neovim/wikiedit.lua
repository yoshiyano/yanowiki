-- wikiedit.lua — wikiSystem の編集画面と同期する（Neovim のプラグイン）
--
-- 更新: 2026-10-14 21:43 +09:00
--
-- 使いかた（詳しくは wikiSystem の _system Wiki の「エディタ連動の編集」）:
--
--   ~/.config/nvim/lua/wikiedit.lua に置き、init.lua に書く
--     require("wikiedit").setup()
--
-- 初めての Wiki からつながってきたら、許すかを尋ね、許したアドレスを
-- stdpath("data") の associated_wiki.txt（1行に1つ）に覚える。
--
-- ほかのプラグインは要らない（Neovim 0.9 以上）。プロトコルは Tech/EditorSync の「プロトコル v1」。
-- 編集画面で「外部エディタにつなぐ」を押すと、ページごとにバッファが開く。
--
--   :w                    Wiki の保存を押す
--   :bd                   バッファを閉じる（編集画面には「エディタ側で閉じました」と出る）
--   :WikiEditAttach       添付ファイルを選んで、本文での書きかたを挿入する
--   :WikiEditAttachCopy   選んだ添付ファイルの書きかたを、挿入せずにレジスタにコピーする
--   :WikiEditStop / :WikiEditStart / :WikiEditVersion

local M = {}

M.updated = "2026-10-14 21:43 +09:00"

local uv = vim.uv or vim.loop
local bit = require("bit")

M.config = {
  port = 4100,                 -- 待ち受けるポート番号。編集画面の「設定」の「ポート番号」とそろえる
  autostart = true,            -- setup() で待ち受けを始める
  associated_file = nil,       -- 許した Wiki を覚えるファイル（既定は stdpath("data")/associated_wiki.txt）
  allow_extensions = true,     -- ブラウザ拡張機能（wikiedit）を通した接続も受け付ける
  keep_seconds = 10,           -- 保存などで編集画面が再読み込みされるあいだ、バッファを保つ秒数
  stale_seconds = 45,          -- 編集画面から何も届かないまま、この秒数がたったら「応答なし」とみなす
  takeover_interval = 5,       -- ほかの Neovim が待ち受けているとき、いなくなったかを確かめる間隔（秒）
  display = "tab",             -- バッファの出しかた: "tab"（新しいタブページ）・"split"・"current"・"none"
  filetypes = { markdown = "markdown", pukiwiki = "text" },  -- 書きかたごとの filetype
  ask = nil,                   -- 知らないオリジンを許すかを尋ねる関数（origin → true/false）。既定は confirm()
}

local WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
local SEND_DEBOUNCE = 150
local CURSOR_DEBOUNCE = 200

local server = nil
local watch_timer = nil
local sessions = {}        -- セッション ID → session
local by_buf = {}          -- バッファ番号 → session
local associated = nil     -- 許したオリジン（ファイルから読む）
local denied = {}          -- この Neovim を起動しているあいだ、断ると答えたオリジン
local asking = {}          -- 尋ねている最中のオリジン → 答えを待っている関数の列

local function now()
  local s, us = uv.gettimeofday()
  return s * 1000 + math.floor(us / 1000)
end

local function notify(msg, level)
  vim.notify("wikiedit: " .. msg, level or vim.log.levels.INFO)
end

local function timer_stop(t)
  if t and not t:is_closing() then t:stop(); t:close() end
end

-- ms 後に fn を（Neovim の API を呼べるところで）呼ぶ。止めるためのタイマーを返す
local function later(ms, fn)
  local t = uv.new_timer()
  t:start(ms, 0, vim.schedule_wrap(function()
    timer_stop(t)
    fn()
  end))
  return t
end

---------------------------------------------------------------------------
-- 本文・位置・ハッシュ
-- 本文は改行を LF にそろえた文字列（Lua では UTF-8 のバイト列）。プロトコルの位置は
-- UTF-16 の単位なので、バイトの位置と換算する。

local function hash(text) return vim.fn.sha256(text) end

local function is_cont(b) return b ~= nil and b >= 0x80 and b < 0xC0 end

-- バイト列 S を UTF-16 で数えた長さ（続きのバイトは数えず、4バイトの文字は2と数える）
local function u16_len(s)
  if not s:find("[\128-\255]") then return #s end
  local _, leads = s:gsub("[^\128-\191]", "")
  local _, astral = s:gsub("[\240-\247]", "")
  return leads + astral
end

-- UTF-16 の位置 U を、S のバイトの位置（その前にあるバイト数）にする
local function u16_to_byte(s, u)
  u = math.max(0, math.floor(tonumber(u) or 0))
  if not s:find("[\128-\255]") then return math.min(u, #s) end
  local n, i, len = 0, 1, #s
  while i <= len and n < u do
    local b = s:byte(i)
    local size = (b >= 0xF0 and 4) or (b >= 0xE0 and 3) or (b >= 0xC0 and 2) or 1
    n = n + (size == 4 and 2 or 1)
    i = i + size
  end
  return math.min(i - 1, len)
end

-- 前後で共通する部分を除いた1か所（バイトの位置）。文字の途中では切らない
local function byte_diff(before, after)
  local lb, la = #before, #after
  local max = math.min(lb, la)
  local s = 0
  while s + 64 <= max and before:sub(s + 1, s + 64) == after:sub(s + 1, s + 64) do s = s + 64 end
  while s < max and before:byte(s + 1) == after:byte(s + 1) do s = s + 1 end
  while s > 0 and (is_cont(before:byte(s + 1)) or is_cont(after:byte(s + 1))) do s = s - 1 end
  local eb, ea = lb, la
  while eb - 64 >= s and ea - 64 >= s and before:sub(eb - 63, eb) == after:sub(ea - 63, ea) do
    eb, ea = eb - 64, ea - 64
  end
  while eb > s and ea > s and before:byte(eb) == after:byte(ea) do eb, ea = eb - 1, ea - 1 end
  while eb < lb and is_cont(before:byte(eb + 1)) do eb, ea = eb + 1, ea + 1 end
  return s, eb, after:sub(s + 1, ea)
end

-- 差分を、プロトコルの形（UTF-16 の位置）で
local function diff(before, after)
  local s, e, text = byte_diff(before, after)
  return { start = u16_len(before:sub(1, s)), ["end"] = u16_len(before:sub(1, e)), text = text }
end

local function apply_changes(text, changes)
  for _, ch in ipairs(changes or {}) do
    local s = u16_to_byte(text, ch.start)
    local e = math.max(s, u16_to_byte(text, ch["end"]))
    text = text:sub(1, s) .. tostring(ch.text or "") .. text:sub(e + 1)
  end
  return text
end

local function normalize(text) return (tostring(text or ""):gsub("\r\n?", "\n")) end

---------------------------------------------------------------------------
-- WebSocket の接続を始めるときの SHA-1・base64（Neovim 0.9 には base64 が無いので書く）

local function sha1(msg)
  local band, bor, bxor, bnot = bit.band, bit.bor, bit.bxor, bit.bnot
  local lshift, rshift, rol, tobit = bit.lshift, bit.rshift, bit.rol, bit.tobit
  local h0, h1, h2, h3, h4 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0
  local ml = #msg * 8
  local tail = {}
  for i = 7, 0, -1 do tail[#tail + 1] = string.char(math.floor(ml / 2 ^ (8 * i)) % 256) end
  msg = msg .. "\128" .. string.rep("\0", (55 - #msg) % 64) .. table.concat(tail)
  local w = {}
  for chunk = 1, #msg, 64 do
    for i = 0, 15 do
      local a, b, c, d = msg:byte(chunk + 4 * i, chunk + 4 * i + 3)
      w[i] = bor(lshift(a, 24), lshift(b, 16), lshift(c, 8), d)
    end
    for i = 16, 79 do w[i] = rol(bxor(w[i - 3], w[i - 8], w[i - 14], w[i - 16]), 1) end
    local a, b, c, d, e = h0, h1, h2, h3, h4
    for i = 0, 79 do
      local f, k
      if i < 20 then f, k = bor(band(b, c), band(bnot(b), d)), 0x5A827999
      elseif i < 40 then f, k = bxor(b, c, d), 0x6ED9EBA1
      elseif i < 60 then f, k = bor(band(b, c), band(b, d), band(c, d)), 0x8F1BBCDC
      else f, k = bxor(b, c, d), 0xCA62C1D6 end
      local temp = tobit(rol(a, 5) + f + e + k + w[i])
      e, d, c, b, a = d, c, rol(b, 30), a, temp
    end
    h0, h1, h2, h3, h4 = tobit(h0 + a), tobit(h1 + b), tobit(h2 + c), tobit(h3 + d), tobit(h4 + e)
  end
  local out = {}
  for _, h in ipairs({ h0, h1, h2, h3, h4 }) do
    out[#out + 1] = string.char(band(rshift(h, 24), 255), band(rshift(h, 16), 255),
                                band(rshift(h, 8), 255), band(h, 255))
  end
  return table.concat(out)
end

local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

local function base64(data)
  local out = {}
  for i = 1, #data, 3 do
    local a, b, c = data:byte(i, i + 2)
    local n = a * 65536 + (b or 0) * 256 + (c or 0)
    local s = ""
    for j = 3, 0, -1 do
      local v = math.floor(n / 64 ^ j) % 64
      s = s .. B64:sub(v + 1, v + 1)
    end
    if not b then s = s:sub(1, 2) .. "==" elseif not c then s = s:sub(1, 3) .. "=" end
    out[#out + 1] = s
  end
  return table.concat(out)
end

---------------------------------------------------------------------------
-- 知らないオリジンからの接続を尋ねる

local function associated_path()
  return M.config.associated_file or (vim.fn.stdpath("data") .. "/associated_wiki.txt")
end

local function load_associated()
  associated = {}
  local f = io.open(associated_path(), "r")
  if not f then return end
  for line in f:lines() do
    line = vim.trim(line)
    if line ~= "" and not line:match("^#") then associated[line] = true end
  end
  f:close()
end

local function save_associated()
  local path = associated_path()
  vim.fn.mkdir(vim.fn.fnamemodify(path, ":h"), "p")
  local f = io.open(path, "w")
  if not f then notify("覚えておくファイルに書けません: " .. path, vim.log.levels.WARN); return end
  f:write("# wikiedit がつないでよいと覚えた Wiki のオリジン（1行に1つ）。消したいものは消してよい。\n")
  local list = vim.tbl_keys(associated)
  table.sort(list)
  for _, o in ipairs(list) do f:write(o, "\n") end
  f:close()
end

-- ORIGIN を尋ねずに受けてよいか。localhost・127.0.0.1（ポート番号は問わない）と、覚えたもの
local function origin_allowed(origin)
  if not origin then return false end
  if origin:match("^http://localhost$") or origin:match("^http://localhost:%d+$")
     or origin:match("^http://127%.0%.0%.1$") or origin:match("^http://127%.0%.0%.1:%d+$") then
    return true
  end
  if not associated then load_associated() end
  return associated[origin] == true
end

local function default_ask(origin)
  return vim.fn.confirm("wikiedit: " .. origin .. " からの接続を許しますか？", "&Yes\n&No", 2) == 1
end

-- ORIGIN を許すかを決め、CALLBACK に true か false を渡す。知らなければ尋ねる。
-- 同じオリジンの接続が重なっても1回だけ尋ねる
local function decide(origin, callback)
  if origin_allowed(origin) then callback(true); return end
  if not origin or denied[origin] then callback(false); return end
  if asking[origin] then table.insert(asking[origin], callback); return end
  asking[origin] = { callback }
  vim.schedule(function()
    local called, answer = pcall(M.config.ask or default_ask, origin)
    local ok = called and answer == true
    local waiters = asking[origin]
    asking[origin] = nil
    if ok then
      associated[origin] = true
      save_associated()
    else
      denied[origin] = true
    end
    for _, cb in ipairs(waiters) do cb(ok) end
  end)
end

local function url_origin(url)
  return type(url) == "string" and url:match("^(%a[%w+.-]*://[^/]+)") or nil
end

---------------------------------------------------------------------------
-- WebSocket（待ち受ける側を、vim.uv だけで持つ）

local Conn = {}
Conn.__index = Conn

local on_hello  -- 下で定義する

function Conn.new(tcp)
  local self = setmetatable({ tcp = tcp, buf = "", frag = {}, open = false, pending = false,
                              closed = false, bye = false, session = nil, via_extension = false }, Conn)
  tcp:read_start(function(err, chunk)
    vim.schedule(function()
      if err or not chunk then self:on_close() else self:feed(chunk) end
    end)
  end)
  return self
end

function Conn:write(data)
  if not self.closed and not self.tcp:is_closing() then self.tcp:write(data) end
end

-- 書いたものを送り終えてから閉じる
function Conn:finish()
  if self.tcp:is_closing() then return end
  self.tcp:read_stop()
  self.tcp:shutdown(function() if not self.tcp:is_closing() then self.tcp:close() end end)
  self:on_close()
end

function Conn:send_frame(opcode, payload)
  local n = #payload
  local head
  if n < 126 then head = string.char(0x80 + opcode, n)
  elseif n < 65536 then head = string.char(0x80 + opcode, 126, math.floor(n / 256), n % 256)
  else
    local b = {}
    for i = 7, 0, -1 do b[#b + 1] = math.floor(n / 2 ^ (8 * i)) % 256 end
    head = string.char(0x80 + opcode, 127, unpack(b))
  end
  self:write(head .. payload)
end

function Conn:send(obj)
  obj.t = now()
  self:send_frame(1, vim.json.encode(obj))
end

function Conn:close()
  if self.closed then return end
  self.bye = true
  self:send_frame(8, "")
  self:finish()
end

function Conn:feed(chunk)
  self.buf = self.buf .. chunk
  if self.pending then return end           -- 答えを待っている
  if not self.open then
    local e = self.buf:find("\r\n\r\n", 1, true)
    if not e then return end
    local head = self.buf:sub(1, e - 1)
    self.buf = self.buf:sub(e + 4)
    self:handshake(head)
    return
  end
  self:read_frames()
end

function Conn:handshake(head)
  local headers = {}
  for line in head:gmatch("[^\r\n]+") do
    local k, v = line:match("^([^:]+):%s*(.-)%s*$")
    if k then headers[k:lower()] = v end
  end
  local key, origin = headers["sec-websocket-key"], headers["origin"]
  if not key then
    self:write("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
    self:finish()
    return
  end
  local function accept()
    self:write("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" ..
               "Sec-WebSocket-Accept: " .. base64(sha1(key .. WS_GUID)) .. "\r\n\r\n")
    self.open = true
    self:read_frames()
  end
  if M.config.allow_extensions and origin and (origin:match("^chrome%-extension://") or origin:match("^moz%-extension://")) then
    -- 拡張機能を通した接続。ページのオリジンは hello で確かめる
    self.via_extension = true
    accept()
    return
  end
  if origin_allowed(origin) then accept(); return end
  -- 知らないオリジン。答えが出るまで応答を保留する
  self.pending = true
  decide(origin, function(ok)
    self.pending = false
    if self.closed then return end
    if ok then accept()
    else
      notify((origin or "?") .. " からの接続を断りました")
      self:write("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
      self:finish()
    end
  end)
end

local function unmask(payload, mask)
  local out, m = {}, { mask:byte(1, 4) }
  local bxor = bit.bxor
  for i = 1, #payload, 4096 do
    local part = { payload:byte(i, math.min(#payload, i + 4095)) }
    for j = 1, #part do part[j] = bxor(part[j], m[(i + j - 2) % 4 + 1]) end
    out[#out + 1] = string.char(unpack(part))
  end
  return table.concat(out)
end

function Conn:read_frames()
  local data = self.buf
  while #data >= 2 and not self.closed do
    local b1, b2 = data:byte(1, 2)
    local fin, op = b1 >= 0x80, b1 % 16
    local masked, n, pos = b2 >= 0x80, b2 % 128, 3
    if n == 126 then
      if #data < 4 then break end
      local x, y = data:byte(3, 4); n = x * 256 + y; pos = 5
    elseif n == 127 then
      if #data < 10 then break end
      n = 0
      for i = 3, 10 do n = n * 256 + data:byte(i) end
      pos = 11
    end
    local mask
    if masked then mask = data:sub(pos, pos + 3); pos = pos + 4 end
    if #data < pos + n - 1 then break end
    local payload = data:sub(pos, pos + n - 1)
    if mask then payload = unmask(payload, mask) end
    data = data:sub(pos + n)
    if op == 1 or op == 0 then
      table.insert(self.frag, payload)
      if fin then
        local text = table.concat(self.frag)
        self.frag = {}
        self:on_text(text)
      end
    elseif op == 8 then
      self.buf = ""
      self:send_frame(8, "")
      self:finish()
      return
    elseif op == 9 then
      self:send_frame(10, payload)
    end
  end
  self.buf = data
end

function Conn:on_text(text)
  local ok, m = pcall(vim.json.decode, text, { luanil = { object = true, array = true } })
  if not ok or type(m) ~= "table" or type(m.type) ~= "string" then return end
  if m.type == "ping" then
    local t1 = now()
    self:send({ type = "pong", t0 = m.t, t1 = t1, t2 = now() })
  elseif m.type == "hello" then
    on_hello(self, m)
  end
  if self.session and self.session.conn == self then self.session:touch() end
  if m.type == "ping" or m.type == "hello" then return end
  if self.session and self.session.conn == self then
    self.session:on_message(m)
  end
end

function Conn:on_close()
  if self.closed then return end
  self.closed = true
  local s = self.session
  if s and s.conn == self then s:on_disconnect(self.bye) end
end

---------------------------------------------------------------------------
-- 1つの編集画面（タブのセッション ID ごと）と、それを映すバッファ

local Session = {}
Session.__index = Session

local function buf_text(buf)
  return table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n")
end

-- バイトの位置 OFF を、(行, 列) にする（どちらも 0 から）
local function byte_to_pos(text, off)
  local row, line_start = 0, 1
  while true do
    local nl = text:find("\n", line_start, true)
    if not nl or nl > off then break end
    row, line_start = row + 1, nl + 1
  end
  return row, off - line_start + 1
end

local function buf_name(page, id)
  local host = (type(page.url) == "string" and page.url:match("^%a[%w+.-]*://([^/]+)")) or "wiki"
  local parts = {}
  for p in tostring(page.title or page.path or "page"):gmatch("[^/]+") do
    if p ~= "." and p ~= ".." then parts[#parts + 1] = p end
  end
  local name = "wikiedit://" .. host .. "/" .. (#parts > 0 and table.concat(parts, "/") or "page")
  local other = vim.fn.bufnr("^" .. vim.fn.escape(name, "\\/.*$^~[]") .. "$")
  if other ~= -1 and not (by_buf[other] and by_buf[other].id == id) then
    name = name .. "?" .. id   -- 同じページを別のタブでも開いている。別のバッファにする
  end
  return name
end

function Session.new(id)
  return setmetatable({ id = id, conn = nil, buf = nil, page = nil, shadow = nil, modified = now(),
                        offset = 0, sent_state = false, attachments = {}, applying = false,
                        send_timer = nil, cursor_timer = nil, keep_timer = nil, last_cursor = nil,
                        link = nil, last_recv = 0, unsent = false, expect_reload = 0,
                        disposed = false }, Session)
end

function Session:send(obj) if self.conn then self.conn:send(obj) end end

function Session:valid() return self.buf and vim.api.nvim_buf_is_valid(self.buf) end

function Session:text() return self:valid() and buf_text(self.buf) or self.shadow end

function Session:to_local(t) return type(t) == "number" and t + self.offset or now() end

function Session:set_page(page)
  local name = buf_name(page, self.id)
  if vim.api.nvim_buf_get_name(self.buf) ~= name then pcall(vim.api.nvim_buf_set_name, self.buf, name) end
  local ft = M.config.filetypes[page.markup] or "text"
  if vim.bo[self.buf].filetype ~= ft then vim.bo[self.buf].filetype = ft end
  self.page = page
end

function Session:create_buffer()
  local buf = vim.api.nvim_create_buf(true, false)
  self.buf = buf
  by_buf[buf] = self
  vim.bo[buf].buftype = "acwrite"
  vim.bo[buf].swapfile = false
  local group = vim.api.nvim_create_augroup("wikiedit_buf_" .. buf, { clear = true })
  vim.api.nvim_create_autocmd("BufWriteCmd", { group = group, buffer = buf, callback = function()
    local s = by_buf[buf]
    if s then s:save() end
  end })
  vim.api.nvim_create_autocmd("BufWinEnter", { group = group, buffer = buf, callback = function()
    local s = by_buf[buf]
    if s then s:update_display() end
  end })
  vim.api.nvim_create_autocmd({ "CursorMoved", "CursorMovedI" }, { group = group, buffer = buf, callback = function()
    local s = by_buf[buf]
    if s then s:on_cursor_moved() end
  end })
  vim.api.nvim_create_autocmd({ "BufDelete", "BufWipeout" }, { group = group, buffer = buf, callback = function(ev)
    local s = by_buf[buf]
    if s and not s.disposed then s:dispose(true, true) end
    -- :bd は名前を残したままにするので、消し切る（同じページをもう一度開いたときに名前がぶつからないように）
    if ev.event == "BufDelete" then
      vim.schedule(function()
        if vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end
      end)
    end
  end })
  vim.api.nvim_buf_attach(buf, false, {
    on_lines = function()
      local s = by_buf[buf]
      if not s or s.disposed then return true end
      if s.applying then return end
      vim.schedule(function() s:on_local_change() end)
    end,
  })
end

function Session:show()
  local display = M.config.display
  if display == "none" or #vim.fn.win_findbuf(self.buf) > 0 then return end
  if display == "split" then vim.cmd("sbuffer " .. self.buf)
  elseif display == "current" then vim.api.nvim_set_current_buf(self.buf)
  else vim.cmd("tab sbuffer " .. self.buf) end
end

-- 届いた本文をバッファに反映する。シャドウは先に新しくし、当てた変更を送り返さないようにする
function Session:set_text(next_text)
  self.shadow = next_text
  if not self:valid() then return end
  local current = buf_text(self.buf)
  if current == next_text then return end
  local s, e, ins = byte_diff(current, next_text)
  local r1, c1 = byte_to_pos(current, s)
  local r2, c2 = byte_to_pos(current, e)
  self.applying = true
  local ok, err = pcall(vim.api.nvim_buf_set_text, self.buf, r1, c1, r2, c2, vim.split(ins, "\n", { plain = true }))
  self.applying = false
  if not ok then
    self.applying = true
    vim.api.nvim_buf_set_lines(self.buf, 0, -1, false, vim.split(next_text, "\n", { plain = true }))
    self.applying = false
    notify("本文を全体で置き換えました（" .. tostring(err) .. "）", vim.log.levels.DEBUG)
  end
  vim.bo[self.buf].modified = false
end

function Session:on_hello(conn, m, resumed)
  timer_stop(self.keep_timer)
  if self.conn and self.conn ~= conn then local old = self.conn; self.conn = nil; old:close() end
  self.conn = conn
  conn.session = self
  local page = type(m.page) == "table" and m.page or {}
  local text = normalize(m.text)
  local same_page = resumed and self.page and self.page.path == page.path and self:valid()
  local was_link = self.link
  local mine = self:valid() and buf_text(self.buf) or nil
  local base = self.shadow
  local follow = nil
  self.attachments = type(m.attachments) == "table" and m.attachments or {}
  self.sent_state = false
  if resumed and not same_page and base and mine and mine ~= base then
    -- 前のページの、まだ送っていない変更は消さずに控える
    self:keep_backup(mine, "別のページへ移る前の、送っていない変更")
  end
  if not same_page then
    -- 新しいページ（か初めて）: ページの本文で始める。名前と filetype もページに合わせる
    if not self:valid() then self:create_buffer() end
    self:set_page(page)
    self:set_text(text)
    self.modified = now()
  else
    -- 同じページを引き継いだ。最後にそろえた本文（シャドウ）を基準に、どちらが変わったかで決める
    self.page = page
    if not base or mine == base then
      self:set_text(text)                       -- エディタは変わっていない: 編集画面の本文にそろえる
    elseif text == base then
      follow = "edit"                           -- 編集画面は変わっていない: welcome のあとに送る
    elseif self:to_local(m.modified) > self.modified then
      self:keep_backup(mine)                    -- 両方: 編集画面が新しい。エディタの分は控える
      self:set_text(text)
      self.modified = self:to_local(m.modified)
    else
      follow = "full"                           -- 両方: エディタが新しい。welcome のあとに全文を送る
    end
  end
  self.shadow = text
  self.unsent = false
  self.expect_reload = 0
  self.last_recv = now()
  self:set_link("connected")
  self:update_display()   -- 添付ファイルの数を出し直す
  local v = vim.version()
  -- welcome の hash は、いつも編集画面から届いた本文のもの（編集画面に時刻で決めさせない）。
  -- エディタの変更は、このあとの edit か full で送る
  conn:send({ type = "welcome", v = 1,
              editor = string.format("Neovim %d.%d.%d・wikiedit %s", v.major, v.minor, v.patch, M.updated:sub(1, 16)),
              resumed = resumed and true or false, t_recv = now(),
              hash = hash(text), modified = self.modified })
  if follow == "edit" then
    self:flush()
    notify("つなぎ直しました。切れているあいだの変更を編集画面に送りました")
  elseif follow == "full" then
    self:send_full()
    notify("つなぎ直しました。両方で変更があり、エディタのほうが新しいので、エディタの本文にそろえました")
  elseif same_page and (was_link == "stale" or was_link == "disconnected") then
    notify("つなぎ直しました")
  end
  self:show()
  if not same_page then
    -- 新しいページはカーソルを先頭に置く（同じタブでページを移ったときは、前の位置が残るため）
    for _, win in ipairs(vim.fn.win_findbuf(self.buf)) do pcall(vim.api.nvim_win_set_cursor, win, { 1, 0 }) end
  end
end

function Session:on_message(m)
  if self.disposed then return end
  local t = m.type
  if t == "clock" then
    self.offset = tonumber(m.offset) or 0
  elseif t == "attachments" then
    self.attachments = type(m.attachments) == "table" and m.attachments or {}
    self:update_display()
  elseif t == "edit" then
    self:flush()
    if m.from ~= hash(self.shadow) then self:send_state(); return end
    local next_text = apply_changes(self.shadow, m.changes)
    if hash(next_text) ~= m.to then self:send_state(); return end
    self.modified = self:to_local(m.modified)
    self:set_text(next_text)
  elseif t == "state" then
    self:resolve(m)
  elseif t == "full" then
    -- 置き換える前に手元の分を送らない（送ると、編集画面とエディタの本文がずれる）。手元の分は控える
    timer_stop(self.send_timer)
    local text = normalize(m.text)
    local current = self:text()
    if text ~= current then self:keep_backup(current) end
    self.sent_state = false
    self.modified = self:to_local(m.modified)
    self:set_text(text)
  elseif t == "cursor" then
    self:set_cursor(m.start, m["end"])
  elseif t == "reload" then
    -- 編集画面が再読み込みする。このあと切れても、同じセッション ID で戻るのを待つ
    self.expect_reload = now()
  elseif t == "bye" then
    if self.conn then self.conn.bye = true end
    self:dispose(false)
  end
end

-- 食い違った。新しいほうが full を送る（同じ時刻ならエディタ側が正）
function Session:resolve(m)
  if m.hash == hash(self.shadow) then self.sent_state = false; return end
  if self.modified >= self:to_local(m.modified) then
    self:send_full()
  elseif not self.sent_state then
    self:send_state()
  end
end

-- いまのバッファの全文を full で送り、シャドウをそろえる
function Session:send_full()
  timer_stop(self.send_timer)
  local text = self:text()
  self.shadow = text
  self:send({ type = "full", text = text, hash = hash(text), modified = self.modified })
end

function Session:send_state()
  self.sent_state = true
  self:send({ type = "state", hash = hash(self.shadow), modified = self.modified })
end

-- 置き換える前の本文を、控えのバッファに残す
function Session:keep_backup(text, what)
  local name = vim.api.nvim_buf_get_name(self.buf) .. " 控え"
  local b = vim.fn.bufnr("^" .. vim.fn.escape(name, "\\/.*$^~[]") .. "$")
  if b == -1 then
    b = vim.api.nvim_create_buf(true, true)
    pcall(vim.api.nvim_buf_set_name, b, name)
  end
  vim.api.nvim_buf_set_lines(b, 0, -1, false, vim.split(text, "\n", { plain = true }))
  notify((what or "編集画面の内容が新しかったので置き換えました") .. "（元の内容は「" .. name .. "」に残しました）",
         vim.log.levels.WARN)
end

-- 手元の変更
function Session:on_local_change()
  if self.disposed or self.applying or not self.shadow then return end
  if self:text() == self.shadow then return end   -- 届いたものを当てた
  self.modified = now()
  if not self:sendable() and not self.unsent then self.unsent = true; self:update_display() end
  timer_stop(self.send_timer)
  self.send_timer = later(SEND_DEBOUNCE, function() self:flush(); self:send_cursor() end)
end

-- 手元の変更を、待たずに送る（届いたものを当てる前に、シャドウをそろえておく）
function Session:flush(conn)
  timer_stop(self.send_timer)
  if not conn and not self:sendable() then return end
  conn = conn or self.conn
  if not conn or not self.shadow or not self:valid() then return end
  local text = buf_text(self.buf)
  if text ~= self.shadow then
    conn:send({ type = "edit", from = hash(self.shadow), to = hash(text),
                changes = { diff(self.shadow, text) }, modified = self.modified })
    self.shadow = text
  end
  -- 本文は打つたびに編集画面へ送っているので、変更フラグは残さない（閉じるときに訊かれないように）
  vim.bo[self.buf].modified = false
end

function Session:save()
  self:flush()
  if self.conn then
    self:send({ type = "save" })
    -- 保存すると編集画面は再読み込みする。reload が届かなくても、通信の切断とは扱わない
    self.expect_reload = now()
  else notify("編集画面とつながっていません") end
  if self:valid() then vim.bo[self.buf].modified = false end
end

-- カーソル（Neovim はバイトの位置。UTF-16 の位置に換算する）
function Session:cursor_u16()
  local win = vim.fn.win_findbuf(self.buf)[1]
  if not win then return nil end
  if vim.api.nvim_get_current_buf() == self.buf then win = vim.api.nvim_get_current_win() end
  local row, col = unpack(vim.api.nvim_win_get_cursor(win))
  local off = vim.api.nvim_buf_get_offset(self.buf, row - 1) + col
  return u16_len(buf_text(self.buf):sub(1, off))
end

function Session:send_cursor()
  if not self:sendable() or not self:valid() then return end
  local c = self:cursor_u16()
  if not c or c == self.last_cursor then return end
  self.last_cursor = c
  self:send({ type = "cursor", start = c, ["end"] = c })
end

function Session:on_cursor_moved()
  timer_stop(self.cursor_timer)
  self.cursor_timer = later(CURSOR_DEBOUNCE, function()
    if self:valid() and self:text() == self.shadow then self:send_cursor() end  -- 打った分は、本文と一緒に送る
  end)
end

-- 編集画面のカーソルに合わせる（範囲のときは終わりに置く）
function Session:set_cursor(_, finish)
  if not self:valid() then return end
  local text = buf_text(self.buf)
  local row, col = byte_to_pos(text, u16_to_byte(text, finish))
  for _, win in ipairs(vim.fn.win_findbuf(self.buf)) do
    pcall(vim.api.nvim_win_set_cursor, win, { row + 1, col })
  end
  self.last_cursor = u16_len(text:sub(1, u16_to_byte(text, finish)))
end

-- 編集画面とつながりが切れた。bye でなければ、再読み込み（保存・ページの切り替え）を待つ
function Session:on_disconnect(bye)
  self.conn = nil
  timer_stop(self.send_timer)
  if self.disposed then return end
  if bye then self:dispose(false); return end
  self:set_link(self:reload_expected() and "reloading" or "disconnected")
  timer_stop(self.keep_timer)
  self.keep_timer = later(M.config.keep_seconds * 1000, function()
    if self.conn or self.disposed then return end
    if self:valid() and self.shadow and buf_text(self.buf) ~= self.shadow then
      -- 送っていない変更がある: 閉じずに残し、同じタブの編集画面がつなぎ直すのを待つ
      self:set_link("disconnected")
      notify("編集画面との通信が切れたままです。送っていない変更があるので、閉じずに残します", vim.log.levels.WARN)
    else
      self:dispose(false)
    end
  end)
end

---------------------------------------------------------------------------
-- 編集画面とのつながり（編集は止めない）

-- 編集画面の再読み込みを待っているか（reload を受けた・保存を送ってから 15 秒以内）
function Session:reload_expected() return now() - self.expect_reload < 15000 end

-- いま編集画面へ送ってよいか。応答なしのあいだは送らない
function Session:sendable() return self.conn ~= nil and not self.conn.closed and self.link == "connected" end

local LINK_TEXT = {
  reloading = "再読み込み中（保存など。すぐ戻ります）",
  stale = "応答なし（編集は続けられます。応答があったら送ります）",
  disconnected = "切断（編集は続けられます。編集画面がつなぎ直したら送ります）",
}

-- winbar に、ページの添付ファイルの数（0 も出す）と、つながっていないときはその状態を出す
function Session:update_display()
  if not self:valid() then return end
  local n = #(self.attachments or {})
  local text = "wikiedit: 添付 " .. n .. "件"
  local link = LINK_TEXT[self.link]
  if link then text = text .. " ｜ " .. link .. (self.unsent and "・未送信あり" or "") end
  vim.b[self.buf].wikiedit_state = self.link
  vim.b[self.buf].wikiedit_attachments = n
  local bar = text:gsub("%%", "%%%%")
  for _, win in ipairs(vim.fn.win_findbuf(self.buf)) do
    -- setlocal にあたる。同じウィンドウでほかのバッファに替えたとき、表示を持ち越さない
    pcall(vim.api.nvim_set_option_value, "winbar", bar, { scope = "local", win = win })
  end
end

function Session:set_link(state)
  if state == self.link then return end
  local old = self.link
  self.link = state
  if state == "disconnected" then
    notify("編集画面との通信が切れました。編集は続けられます（つながったら送ります）", vim.log.levels.WARN)
  elseif state == "stale" then
    notify("編集画面から " .. M.config.stale_seconds .. " 秒応答がありません。編集は続けられます", vim.log.levels.WARN)
  elseif state == "connected" and old == "stale" then
    notify("編集画面の応答が戻りました")
  end
  self:update_display()
end

-- 編集画面から何か届いた。応答なしだったら、ためていた変更を送る
function Session:touch()
  self.last_recv = now()
  if self.link == "stale" then
    self:set_link("connected")
    self.unsent = false
    self:update_display()
    vim.schedule(function() if not self.disposed then self:flush(); self:send_cursor() end end)
  end
end

local function check_stale()
  for _, s in pairs(sessions) do
    if s.link == "connected" and s.conn and now() - s.last_recv > M.config.stale_seconds * 1000 then
      s:set_link("stale")
    end
  end
end

-- 終える。say_closed なら、編集画面に「エディタ側で閉じました」と知らせる（バッファを閉じたとき）
function Session:dispose(say_closed, buffer_gone)
  if self.disposed then return end
  self.disposed = true
  for _, t in ipairs({ self.keep_timer, self.send_timer, self.cursor_timer }) do timer_stop(t) end
  if sessions[self.id] == self then sessions[self.id] = nil end
  local buf = self.buf
  if self.conn then
    local conn = self.conn
    self.conn = nil
    conn.session = nil
    if say_closed and not buffer_gone then self:flush(conn) end
    if say_closed then conn:send({ type = "closed" }) end
    conn:close()
  end
  if buf then by_buf[buf] = nil end
  if buf and not buffer_gone and vim.api.nvim_buf_is_valid(buf) then
    pcall(vim.api.nvim_buf_delete, buf, { force = true })
  end
end

local function start_session(conn, m)
  local id = tostring(m.session or "")
  if id == "" then conn:close(); return end
  local s = sessions[id]
  local resumed = s ~= nil and not s.disposed
  if not resumed then s = Session.new(id); sessions[id] = s end
  s:on_hello(conn, m, resumed)
end

on_hello = function(conn, m)
  if not conn.via_extension then start_session(conn, m); return end
  -- 拡張機能を通した接続は、hello に書かれたページのオリジンで決める
  local origin = url_origin(type(m.page) == "table" and m.page.url or nil)
  decide(origin, function(ok)
    if conn.closed then return end
    if ok then start_session(conn, m)
    else
      notify((origin or "?") .. " からの接続を断りました")
      conn:close()
    end
  end)
end

---------------------------------------------------------------------------
-- 添付ファイル

local function current_session()
  return by_buf[vim.api.nvim_get_current_buf()]
end

function M.attachment(copy)
  local s = current_session()
  if not s then notify("Wiki のバッファで使ってください"); return end
  local items = s.attachments or {}
  if #items == 0 then notify("このページに添付ファイルはありません"); return end
  local win = vim.api.nvim_get_current_win()
  vim.ui.select(items, {
    prompt = copy and "コピーする添付ファイル: " or "挿入する添付ファイル: ",
    format_item = function(a)
      return string.format("%s  %s %s", a.name or "", a.kind or "", a.size or "")
    end,
  }, function(item)
    if not item then return end
    local ref = tostring(item.ref or item.name or "")
    if copy then
      vim.fn.setreg('"', ref)
      pcall(vim.fn.setreg, "+", ref)
      notify(ref .. " をコピーしました")
    elseif vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_set_current_win(win)
      vim.api.nvim_put({ ref }, "c", true, true)
    end
  end)
end

---------------------------------------------------------------------------
-- 起動・停止

local function listen()
  local tcp = uv.new_tcp()
  local ok = pcall(function()
    assert(tcp:bind("127.0.0.1", M.config.port))
    assert(tcp:listen(16, function(err)
      if err then return end
      local client = uv.new_tcp()
      tcp:accept(client)
      vim.schedule(function() Conn.new(client) end)
    end))
  end)
  if not ok then tcp:close(); return nil end
  return tcp
end

-- 編集画面からの接続を待ち受ける。同じポートでほかの Neovim が待ち受けていれば、
-- takeover_interval 秒ごとに確かめ、いなくなったら引き継ぐ
local stale_timer = nil

function M.start()
  if not associated then load_associated() end
  if not stale_timer then
    stale_timer = uv.new_timer()
    stale_timer:start(10000, 10000, vim.schedule_wrap(check_stale))
  end
  if server then return end
  server = listen()
  if server then return end
  notify(M.config.port .. " はほかのエディタが待ち受けています。" .. M.config.takeover_interval ..
         " 秒ごとに確かめ、いなくなったら引き継ぎます")
  if watch_timer then return end
  watch_timer = uv.new_timer()
  local ms = M.config.takeover_interval * 1000
  watch_timer:start(ms, ms, vim.schedule_wrap(function()
    if server then return end
    server = listen()
    if server then
      timer_stop(watch_timer)
      watch_timer = nil
      notify("待ち受けていたエディタがいなくなったので、" .. M.config.port .. " を引き継ぎました")
    end
  end))
end

-- 待ち受けをやめ、同期しているバッファを閉じる
function M.stop()
  timer_stop(watch_timer)
  watch_timer = nil
  timer_stop(stale_timer)
  stale_timer = nil
  if server and not server:is_closing() then server:close() end
  server = nil
  for _, s in pairs(vim.tbl_values(sessions)) do s:dispose(false) end
end

function M.version()
  notify(M.updated .. (server and ("（" .. M.config.port .. " で待ち受けています）")
                      or watch_timer and "（ほかのエディタが待ち受けています）" or "（止めています）"))
end

function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})
  local cmd = vim.api.nvim_create_user_command
  cmd("WikiEditStart", M.start, { desc = "wikiedit: 待ち受けを始める" })
  cmd("WikiEditStop", M.stop, { desc = "wikiedit: 待ち受けをやめ、Wiki のバッファを閉じる" })
  cmd("WikiEditVersion", M.version, { desc = "wikiedit: バージョンを表示" })
  cmd("WikiEditAttach", function() M.attachment(false) end, { desc = "wikiedit: 添付ファイルの書きかたを挿入する" })
  cmd("WikiEditAttachCopy", function() M.attachment(true) end, { desc = "wikiedit: 添付ファイルの書きかたをコピーする" })
  vim.api.nvim_create_autocmd("VimLeavePre", { group = vim.api.nvim_create_augroup("wikiedit", { clear = true }),
                                               callback = function() M.stop() end })
  if M.config.autostart then M.start() end
end

-- 試験から中身を確かめるための入口（使う人は要らない）
M._test = { sessions = sessions, by_buf = by_buf, sha1 = sha1, base64 = base64, diff = diff,
            apply_changes = apply_changes, u16_len = u16_len, u16_to_byte = u16_to_byte }

return M
