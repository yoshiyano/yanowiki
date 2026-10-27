;;; wikiedit.el --- wikiSystem の編集画面と同期する -*- lexical-binding: t -*-

;; 更新: 2026-10-14 21:43 +09:00

;; 使いかた（詳しくは wikiSystem の _system Wiki の「エディタ連動の編集」）:
;;
;;   (add-to-list 'load-path "<このファイルを置いたフォルダ>")
;;   (require 'wikiedit)
;;   (wikiedit-start)
;;
;; 初めての Wiki からつながってきたら、ミニバッファで許すかを尋ね、許したアドレスを
;; `wikiedit-associated-file'（既定は ~/.emacs.d/associated_wiki.el）に覚える。
;;
;; ほかのパッケージは要らない（Emacs 28 以上）。プロトコルは Tech/EditorSync の「プロトコル v1」。
;; 編集画面で「外部エディタにつなぐ」を押すと、ページごとにバッファが開く。
;;
;;   C-x C-s   Wiki の保存を押す
;;   C-c C-c   バッファを閉じる（編集画面には「エディタ側で閉じました」と出る）
;;   C-c C-a   添付ファイルを選んで、本文での書きかたを挿入する（C-u を付けると kill-ring にコピーする）

;;; Code:

(require 'cl-lib)
(require 'json)

(defconst wikiedit-updated "2026-10-14 21:43 +09:00"
  "このファイルを更新した日時（冒頭のコメントの「更新:」と同じ）。")

(defun wikiedit-version ()
  "このプラグインを更新した日時を出す。"
  (interactive)
  (message "wikiedit: %s" wikiedit-updated))

(defgroup wikiedit nil
  "wikiSystem の編集画面と同期する。"
  :group 'tools)

(defcustom wikiedit-port 4100
  "待ち受けるポート番号。編集画面の「設定」の「ポート番号」とそろえる。"
  :type 'integer)

(defconst wikiedit--local-origins '("http://localhost" "http://127.0.0.1")
  "尋ねずに受けるオリジン（ポート番号は問わない）。それ以外は初めての接続で尋ねる。")

(defcustom wikiedit-associated-file
  (expand-file-name "associated_wiki.el" user-emacs-directory)
  "つないでよいと答えた Wiki のオリジンを覚えておくファイル。
消したいアドレスは、このファイルから消す。"
  :type 'file)

(defcustom wikiedit-ask-function #'wikiedit--ask
  "知らないオリジンからつながってきたときに、許すかを尋ねる関数。
オリジンの文字列を受け、許すなら non-nil を返す。"
  :type 'function)

(defvar wikiedit-associated-origins nil
  "つないでよいと答えた Wiki のオリジン（`wikiedit-associated-file' に覚える）。")

(defcustom wikiedit-allow-extensions t
"ブラウザ拡張機能（wikiedit）を通した接続を受け付けるか。
受け付けるときも、最初の hello に書かれたページのオリジンで、許すかを決める。"
  :type 'boolean)

(defcustom wikiedit-keep-seconds 10
  "編集画面が切れたあと（保存・ページの切り替え）、バッファを保つ秒数。
タブを閉じたときは編集画面が bye を送るので、待たずに閉じる。これは bye が届かなかったときの備え。"
  :type 'integer)

(defcustom wikiedit-display 'frame
  "バッファの出しかた。`frame' は新しいフレーム、`window' は今のウィンドウ、`none' は出さない。"
  :type '(choice (const frame) (const window) (const none)))

(defcustom wikiedit-mode-alist
  '(("markdown" . markdown-mode) ("pukiwiki" . text-mode))
  "書きかたごとのメジャーモード。無いモードなら `text-mode'。"
  :type '(alist :key-type string :value-type function))

(defcustom wikiedit-takeover-interval 5
  "ほかの Emacs が待ち受けていたとき、いなくなったかを確かめる間隔（秒）。"
  :type 'integer)

(defcustom wikiedit-stale-seconds 45
  "編集画面から何も届かないまま、この秒数がたったら「応答なし」とみなす。
編集画面は 20 秒ごとに ping を送る。応答なしのあいだは変更を送らずにためておき、届いたら送る
（相手が受け取らないまま送ると、送り終わるまで Emacs が待ち続けるため）。"
  :type 'integer)

(defconst wikiedit--guid "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")

(defvar wikiedit--server nil)
(defvar wikiedit--denied nil "この Emacs を起動しているあいだ、断ると答えたオリジン。")
(defvar wikiedit--asking nil "尋ねている最中のオリジン → 答えを待っている関数の列。")
(defvar wikiedit--watch-timer nil
  "ほかの Emacs が待ち受けているあいだ、引き継げるかを確かめるタイマー。")
(defvar wikiedit--sessions (make-hash-table :test 'equal)
  "セッション ID → バッファ。")

;; バッファごとの状態
(defvar-local wikiedit--proc nil)
(defvar-local wikiedit--session nil)
(defvar-local wikiedit--page nil)
(defvar-local wikiedit--shadow nil "最後に編集画面とそろえた本文。")
(defvar-local wikiedit--modified 0 "本文を最後に変えた時刻（この Emacs の時計、ミリ秒）。")
(defvar-local wikiedit--offset 0 "この Emacs の時計 − ページの時計（ミリ秒）。")
(defvar-local wikiedit--applying nil)
(defvar-local wikiedit--sent-state nil)
(defvar-local wikiedit--send-timer nil)
(defvar-local wikiedit--cursor-timer nil)
(defvar-local wikiedit--keep-timer nil)
(defvar-local wikiedit--last-cursor nil)
(defvar-local wikiedit--frame nil)
(defvar-local wikiedit--link nil
  "編集画面とのつながり。`connected'（つながっている）・`stale'（応答なし）・`disconnected'（切れている）。")
(defvar-local wikiedit--last-recv 0 "編集画面から最後に何か届いた時刻（ミリ秒）。")
(defvar-local wikiedit--unsent nil "切れているあいだ・応答なしのあいだに変えた分があるか。")
(defvar-local wikiedit--expect-reload 0
  "編集画面の再読み込みを待っている印（その時刻。ミリ秒）。reload を受けたか、エディタから保存を送った。")
(defvar wikiedit--stale-timer nil "応答なしを見つけるタイマー。")
(defvar-local wikiedit--attachments nil
  "ページの添付ファイルの一覧（hello で届く）。要素は name・kind・size・mtime・ref の alist。")

(defun wikiedit--now () (truncate (* 1000 (float-time))))

;;;; 本文・位置・ハッシュ

(defun wikiedit--hash (text)
  (secure-hash 'sha256 (encode-coding-string text 'utf-8 t)))

(defun wikiedit--astral-p (text)
  (string-match-p "[\U00010000-\U0010FFFF]" text))

(defun wikiedit--u16-length (text)
  "TEXT を UTF-16 で数えた長さ。"
  (if (wikiedit--astral-p text)
      (cl-loop for c across text sum (if (> c #xFFFF) 2 1))
    (length text)))

(defun wikiedit--u16-to-index (text u16)
  "UTF-16 の位置 U16 を、TEXT の文字の位置にする。"
  (if (not (wikiedit--astral-p text))
      (max 0 (min u16 (length text)))
    (let ((i 0) (n 0) (len (length text)))
      (while (and (< i len) (< n u16))
        (setq n (+ n (if (> (aref text i) #xFFFF) 2 1)) i (1+ i)))
      i)))

(defun wikiedit--char-diff (before after)
  "前後で共通する部分を除いた1か所を、文字の位置で返す。(start end-before end-after)。
本文の長さに比例する時間で済む。"
  (let* ((c (compare-strings before nil nil after nil nil))
         (start (if (eq c t) (length before) (1- (abs c))))
         (rb (reverse before)) (ra (reverse after))
         (c2 (compare-strings rb nil nil ra nil nil))
         (suffix (if (eq c2 t) (length before) (1- (abs c2)))))
    (setq suffix (min suffix (- (length before) start) (- (length after) start)))
    (list start (- (length before) suffix) (- (length after) suffix))))

(defun wikiedit--diff (before after)
  "前後で共通する部分を除いた1か所。位置は UTF-16。(start end text) を返す。"
  (pcase-let ((`(,start ,endb ,enda) (wikiedit--char-diff before after)))
    (list (wikiedit--u16-length (substring before 0 start))
          (wikiedit--u16-length (substring before 0 endb))
          (substring after start enda))))

(defun wikiedit--apply-changes (text changes)
  (dolist (ch changes text)
    (let* ((s (wikiedit--u16-to-index text (alist-get 'start ch)))
           (e (max s (wikiedit--u16-to-index text (alist-get 'end ch)))))
      (setq text (concat (substring text 0 s) (or (alist-get 'text ch) "") (substring text e))))))

;;;; WebSocket（標準の機能だけで、サーバーの側を持つ）

(defun wikiedit--origin-allowed (origin)
  "ORIGIN を尋ねずに受けてよいか。localhost・127.0.0.1（ポート番号は問わない）と、覚えたもの。"
  (and origin
       (or (member origin wikiedit-associated-origins)
           (cl-some (lambda (local)
                      (string-match-p (concat "\\`" (regexp-quote local) "\\(:[0-9]+\\)?\\'") origin))
                    wikiedit--local-origins))
       t))

;;;; 知らないオリジンからの接続を尋ねる

(defun wikiedit--ask (origin)
  (y-or-n-p (format "wikiedit: %s からの接続を許しますか？ " origin)))

(defun wikiedit--decide (origin callback)
  "ORIGIN を許すかを決め、CALLBACK に t か nil を渡す。知らなければ尋ねる。
尋ねるのはプロセスの処理を抜けてから（タイマー）。同じオリジンの接続が重なっても1回だけ尋ねる。"
  (cond
   ((wikiedit--origin-allowed origin) (funcall callback t))
   ((or (not origin) (member origin wikiedit--denied)) (funcall callback nil))
   ((assoc origin wikiedit--asking)
    (push callback (cdr (assoc origin wikiedit--asking))))
   (t
    (push (list origin callback) wikiedit--asking)
    (run-at-time
     0 nil
     (lambda ()
       (let ((ok (condition-case nil (funcall wikiedit-ask-function origin) (quit nil)))
             (waiters (cdr (assoc origin wikiedit--asking))))
         (setq wikiedit--asking (assoc-delete-all origin wikiedit--asking))
         (if ok
             (progn (cl-pushnew origin wikiedit-associated-origins :test #'equal)
                    (wikiedit--save-associated))
           (cl-pushnew origin wikiedit--denied :test #'equal))
         (dolist (cb waiters) (funcall cb ok))))))))

(defun wikiedit--load-associated ()
  (when (file-readable-p wikiedit-associated-file)
    (load wikiedit-associated-file t t t)))

(defun wikiedit--save-associated ()
  (with-temp-file wikiedit-associated-file
    (insert ";; wikiedit がつないでよいと覚えた Wiki のオリジン。消したいものは消してよい。\n"
            (format "(setq wikiedit-associated-origins\n      '%S)\n"
                    wikiedit-associated-origins))))

(defun wikiedit--send-frame (proc opcode payload)
  (when (process-live-p proc)
    (let* ((n (length payload))
           (head (cond ((< n 126) (unibyte-string (logior #x80 opcode) n))
                       ((< n 65536) (unibyte-string (logior #x80 opcode) 126 (ash n -8) (logand n 255)))
                       (t (apply #'unibyte-string (logior #x80 opcode) 127
                                 (cl-loop for i from 7 downto 0 collect (logand (ash n (* -8 i)) 255)))))))
      (process-send-string proc (concat head payload)))))

(defun wikiedit--send (proc obj)
  (setf (alist-get 't obj) (wikiedit--now))
  (wikiedit--send-frame
   proc 1 (encode-coding-string (json-serialize obj) 'utf-8 t)))

(defun wikiedit--handshake (proc data)
  "HTTP の要求 DATA に応じる。WebSocket なら t。"
  (let ((headers (make-hash-table :test 'equal)))
    (dolist (line (cdr (split-string data "\r\n" t)))
      (when (string-match "\\`\\([^:]+\\):[ \t]*\\(.*\\)\\'" line)
        (puthash (downcase (match-string 1 line)) (match-string 2 line) headers)))
    (let ((key (gethash "sec-websocket-key" headers))
          (origin (gethash "origin" headers)))
      (cond
       ((not key)
        (process-send-string proc "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        (delete-process proc) nil)
       ((and wikiedit-allow-extensions origin
             (string-match-p "\\`\\(chrome\\|moz\\)-extension://" origin))
        ;; 拡張機能を通した接続。ページのオリジンは hello で確かめる
        (process-put proc :via-extension t)
        (wikiedit--accept proc key))
       ((wikiedit--origin-allowed origin) (wikiedit--accept proc key))
       (t
        ;; 知らないオリジン。答えが出るまで応答を保留する
        (process-put proc :pending t)
        (wikiedit--decide
         origin
         (lambda (ok)
           (when (process-live-p proc)
             (process-put proc :pending nil)
             (if ok
                 (progn (wikiedit--accept proc key)
                        (process-put proc :open t)
                        (wikiedit--filter proc ""))
               (message "wikiedit: %s からの接続を断りました" origin)
               (process-send-string proc "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
               (delete-process proc)))))
        nil)))))

(defun wikiedit--accept (proc key)
  (let ((accept (base64-encode-string
                 (secure-hash 'sha1 (concat key wikiedit--guid) nil nil t))))
    (process-send-string
     proc (concat "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                  "Connection: Upgrade\r\nSec-WebSocket-Accept: " accept "\r\n\r\n"))
    t))

(defun wikiedit--url-origin (url)
  (when (and (stringp url) (string-match "\\`\\([a-z]+://[^/]+\\)" url))
    (match-string 1 url)))

(defun wikiedit--filter (proc chunk)
  (let ((data (concat (or (process-get proc :buf) "") chunk)))
    (cond
     ((process-get proc :pending) (process-put proc :buf data))   ; 答えを待っている
     ((not (process-get proc :open))
        (let ((end (string-search "\r\n\r\n" data)))
          (when end
            (process-put proc :buf (substring data (+ end 4)))
            (when (wikiedit--handshake proc (substring data 0 end))
              (process-put proc :open t)
              (wikiedit--filter proc "")))))
     (t (process-put proc :buf (wikiedit--read-frames proc data))))))

(defun wikiedit--read-frames (proc data)
  "DATA から読めるだけフレームを読み、残りを返す。"
  (catch 'short
    (while (>= (length data) 2)
      (let* ((b1 (aref data 0)) (b2 (aref data 1))
             (fin (/= 0 (logand b1 #x80))) (op (logand b1 #x0f))
             (masked (/= 0 (logand b2 #x80))) (n (logand b2 #x7f)) (pos 2))
        (cond ((= n 126) (when (< (length data) 4) (throw 'short data))
               (setq n (+ (ash (aref data 2) 8) (aref data 3)) pos 4))
              ((= n 127) (when (< (length data) 10) (throw 'short data))
               (setq n 0)
               (dotimes (i 8) (setq n (+ (ash n 8) (aref data (+ 2 i)))))
               (setq pos 10)))
        (let ((mask (when masked (substring data pos (+ pos 4)))))
          (when masked (setq pos (+ pos 4)))
          (when (< (length data) (+ pos n)) (throw 'short data))
          (let ((payload (substring data pos (+ pos n))))
            (when mask
              (dotimes (i n) (aset payload i (logxor (aref payload i) (aref mask (% i 4))))))
            (setq data (substring data (+ pos n)))
            (pcase op
              ((or 1 0)
               (let ((acc (concat (or (process-get proc :frag) "") payload)))
                 (if (not fin) (process-put proc :frag acc)
                   (process-put proc :frag nil)
                   (wikiedit--on-text proc (decode-coding-string acc 'utf-8)))))
              (8 (wikiedit--send-frame proc 8 "") (delete-process proc) (throw 'short ""))
              (9 (wikiedit--send-frame proc 10 payload)))))))
    data))

(defun wikiedit--sentinel (proc _event)
  (unless (process-live-p proc)
    (let ((buf (process-get proc :buffer)))
      (when (buffer-live-p buf)
        (with-current-buffer buf
          (when (eq wikiedit--proc proc)
            (setq wikiedit--proc nil)
            ;; bye が無ければ、再読み込みを待つ
            (unless (process-get proc :bye)
              (wikiedit--set-link (if (wikiedit--reload-expected-p) 'reloading 'disconnected))
              (setq wikiedit--keep-timer
                    (run-at-time wikiedit-keep-seconds nil
                                 #'wikiedit--expire buf)))))))))

(defun wikiedit--expire (buf)
  (when (buffer-live-p buf)
    (with-current-buffer buf
      (cond
       (wikiedit--proc nil)
       ((and wikiedit--shadow (not (equal (wikiedit--buffer-text) wikiedit--shadow)))
        ;; 送っていない変更がある: 閉じずに残し、同じタブの編集画面がつなぎ直すのを待つ
        (wikiedit--set-link 'disconnected)
        (message "wikiedit: 「%s」は編集画面との通信が切れたままです。送っていない変更があるので、閉じずに残します"
                 (buffer-name)))
       (t (wikiedit--close-buffer buf))))))

;;;; 編集画面とのつながり（編集は止めない）

(defun wikiedit--reload-expected-p ()
  "編集画面の再読み込みを待っているか（reload を受けた・保存を送ってから 15 秒以内）。"
  (< (- (wikiedit--now) wikiedit--expect-reload) 15000))

(defun wikiedit--sendable-p ()
  "いま編集画面へ送ってよいか。応答なしのあいだは送らない（送り終わるまで Emacs が待ち続けるため）。"
  (and wikiedit--proc (process-live-p wikiedit--proc) (eq wikiedit--link 'connected)))

(defun wikiedit--set-link (state)
  (unless (eq state wikiedit--link)
    (let ((old wikiedit--link))
      (setq wikiedit--link state)
      (pcase state
        ('reloading nil)   ; 保存などのいつもの再読み込み。知らせない
        ('disconnected
         (message "wikiedit: 「%s」の編集画面との通信が切れました。編集は続けられます（つながったら送ります）"
                  (buffer-name)))
        ('stale
         (message "wikiedit: 「%s」の編集画面から %d 秒応答がありません。編集は続けられます（応答があったら送ります）"
                  (buffer-name) wikiedit-stale-seconds))
        ('connected
         (when (eq old 'stale) (message "wikiedit: 「%s」の編集画面の応答が戻りました" (buffer-name)))))
      (force-mode-line-update))))

(defun wikiedit--touch ()
  "編集画面から何か届いた。応答なしだったら、ためていた変更を送る。"
  (setq wikiedit--last-recv (wikiedit--now))
  (when (eq wikiedit--link 'stale)
    (wikiedit--set-link 'connected)
    (setq wikiedit--unsent nil)
    (run-at-time 0 nil (let ((buf (current-buffer)))
                         (lambda () (when (buffer-live-p buf)
                                      (with-current-buffer buf (wikiedit--flush) (wikiedit--send-cursor))))))))

(defun wikiedit--check-stale ()
  (maphash (lambda (_ buf)
             (when (buffer-live-p buf)
               (with-current-buffer buf
                 (when (and (eq wikiedit--link 'connected) wikiedit--proc
                            (> (- (wikiedit--now) wikiedit--last-recv) (* 1000 wikiedit-stale-seconds)))
                   (wikiedit--set-link 'stale)))))
           wikiedit--sessions))

(defun wikiedit--attach-label ()
  "モード行に出す添付ファイルの数。0 も出す（出ていなければ、まだ一覧が届いていない）。"
  (let ((n (length wikiedit--attachments)))
    (propertize (format " 添付%d" n)
                'help-echo (if (zerop n) "このページに添付ファイルはありません"
                             (concat "添付ファイル（C-c C-a で書きかたを挿入）:\n"
                                     (mapconcat (lambda (a) (or (alist-get 'name a) "")) wikiedit--attachments "\n"))))))

(defun wikiedit--lighter ()
  "モード行の表示。つながっていないときは、編集を止めずに目立たせる。添付ファイルの数も並べる。"
  (concat
   (pcase wikiedit--link
     ('stale (propertize (if wikiedit--unsent " Wiki:応答なし(未送信)" " Wiki:応答なし") 'face 'warning
                         'help-echo "編集画面から応答がありません。編集は続けられ、応答があったら送ります"))
     ('reloading (propertize (if wikiedit--unsent " Wiki:再読み込み中(未送信)" " Wiki:再読み込み中")
                             'help-echo "編集画面が再読み込みしています（保存など）。戻ったら続けます"))
     ('disconnected (propertize (if wikiedit--unsent " Wiki:切断(未送信)" " Wiki:切断") 'face 'error
                                'help-echo "編集画面との通信が切れています。編集は続けられ、同じタブの編集画面がつなぎ直したら送ります"))
     (_ " Wiki"))
   (wikiedit--attach-label)))

;;;; メッセージ

(defun wikiedit--on-text (proc text)
  (let ((m (condition-case nil (json-parse-string text :object-type 'alist :array-type 'list
                                                  :null-object nil :false-object nil)
             (error nil))))
    (when m
      (let ((type (alist-get 'type m)) (buf (process-get proc :buffer)))
        (when (buffer-live-p buf)
          (with-current-buffer buf (when (eq wikiedit--proc proc) (wikiedit--touch))))
        (cond
         ((equal type "hello") (wikiedit--on-hello proc m))
         ((equal type "ping")
          (let ((t1 (wikiedit--now)))
            (wikiedit--send proc `((type . "pong") (t0 . ,(alist-get 't m)) (t1 . ,t1)
                                          (t2 . ,(wikiedit--now))))))
         ((not (buffer-live-p buf)) nil)
         (t (with-current-buffer buf (wikiedit--on-message m))))))))

(defun wikiedit--mode-for (markup)
  (let ((mode (alist-get markup wikiedit-mode-alist nil nil #'equal)))
    (if (and mode (fboundp mode)) mode #'text-mode)))

(defun wikiedit--on-hello (proc m)
  (if (not (process-get proc :via-extension))
      (wikiedit--start-session proc m)
    ;; 拡張機能を通した接続は、hello に書かれたページのオリジンで決める
    (let ((origin (wikiedit--url-origin (alist-get 'url (alist-get 'page m)))))
      (wikiedit--decide
       origin
       (lambda (ok)
         (when (process-live-p proc)
           (if ok (wikiedit--start-session proc m)
             (message "wikiedit: %s からの接続を断りました" origin)
             (delete-process proc))))))))

(defun wikiedit--start-session (proc m)
  (let* ((session (alist-get 'session m))
         (page (alist-get 'page m))
         (text (or (alist-get 'text m) ""))
         (buf (gethash session wikiedit--sessions))
         (resumed (and (buffer-live-p buf) t)))
    (unless resumed
      (setq buf (generate-new-buffer (format "*wiki: %s*" (alist-get 'title page)))))
    (puthash session buf wikiedit--sessions)
    (process-put proc :buffer buf)
    (with-current-buffer buf
      (when (timerp wikiedit--keep-timer) (cancel-timer wikiedit--keep-timer))
      (when (and wikiedit--proc (not (eq wikiedit--proc proc)))
        (delete-process wikiedit--proc))
      (setq wikiedit--proc proc)
      (let* ((same-page (and resumed (equal (alist-get 'path page) (alist-get 'path wikiedit--page))))
             (was-link wikiedit--link)
             (mine (wikiedit--buffer-text))
             (base wikiedit--shadow)
             (follow nil))
        (when (and resumed (not same-page) base (not (equal mine base)))
          ;; 前のページの、まだ送っていない変更は消さずに控える
          (wikiedit--keep-backup mine "別のページへ移る前の、送っていない変更"))
        (unless same-page
          ;; 新しいページ（か初めて）: ページの本文で始める。名前とモードもページに合わせる
          (unless (equal (alist-get 'markup page) (alist-get 'markup wikiedit--page))
            (funcall (wikiedit--mode-for (alist-get 'markup page))))
          (when resumed (rename-buffer (format "*wiki: %s*" (alist-get 'title page)) t))
          (wikiedit--replace-text text)
          ;; 新しいページはカーソルを先頭に置く（本文を挿入すると末に残るため）
          (goto-char (point-min))
          (setq wikiedit--modified (wikiedit--now)))
        (when same-page
          ;; 同じページを引き継いだ。最後にそろえた本文（シャドウ）を基準に、どちらが変わったかで決める
          (cond
           ((or (null base) (equal mine base))
            ;; エディタは変わっていない: 編集画面の本文にそろえる
            (wikiedit--replace-text text))
           ((equal text base)
            ;; 編集画面は変わっていない: 切れているあいだの変更を、welcome のあとに送る
            (setq follow 'edit))
           ((> (wikiedit--to-local (alist-get 'modified m)) wikiedit--modified)
            ;; 両方が変わり、編集画面のほうが新しい: 編集画面の本文にそろえ、エディタの分は控える
            (wikiedit--keep-backup mine)
            (wikiedit--replace-text text)
            (setq wikiedit--modified (wikiedit--to-local (alist-get 'modified m))))
           (t
            ;; 両方が変わり、エディタのほうが新しい: welcome のあとにエディタの全文を送る
            (setq follow 'full))))
        (setq wikiedit--session session
              wikiedit--page page
              wikiedit--attachments (alist-get 'attachments m)
              wikiedit--sent-state nil
              wikiedit--shadow text
              wikiedit--unsent nil
              wikiedit--expect-reload 0
              wikiedit--last-recv (wikiedit--now))
        (wikiedit--set-link 'connected)
        (wikiedit-mode 1)
        (force-mode-line-update)   ; 添付ファイルの数を出し直す
        ;; welcome の hash は、いつも編集画面から届いた本文のもの（編集画面に時刻で決めさせない）。
        ;; エディタの変更は、このあとの edit か full で送る
        (wikiedit--send
         proc `((type . "welcome") (v . 1) (editor . ,(format "Emacs %s・wikiedit %s" emacs-version (substring wikiedit-updated 0 16)))
                (resumed . ,(if resumed t :false)) (t_recv . ,(wikiedit--now))
                (hash . ,(wikiedit--hash text))
                (modified . ,wikiedit--modified)))
        (pcase follow
          ('edit (wikiedit--flush)
                 (message "wikiedit: つなぎ直しました。切れているあいだの変更を編集画面に送りました"))
          ('full (wikiedit--send-full)
                 (message "wikiedit: つなぎ直しました。両方で変更があり、エディタのほうが新しいので、エディタの本文にそろえました（編集画面の内容はブラウザに控えられます）"))
          (_ (when (and same-page (memq was-link '(stale disconnected)))
               (message "wikiedit: つなぎ直しました"))))
        (wikiedit--show buf)
        (unless same-page
          ;; ウィンドウに出ていたバッファ（同じタブでページを移ったとき）は、ウィンドウのカーソルも先頭へ
          (dolist (w (get-buffer-window-list buf nil t)) (set-window-point w (point-min))))))))

(defun wikiedit--show (buf)
  (pcase wikiedit-display
    ('frame
     (with-current-buffer buf
       (if (frame-live-p wikiedit--frame)
           (with-selected-frame wikiedit--frame (switch-to-buffer buf))
         (setq wikiedit--frame (make-frame))
         (with-selected-frame wikiedit--frame (switch-to-buffer buf)))))
    ('window (pop-to-buffer buf))
    (_ nil)))

(defun wikiedit--to-local (time)
  (if (numberp time) (+ time wikiedit--offset) (wikiedit--now)))

(defun wikiedit--buffer-text ()
  (buffer-substring-no-properties (point-min) (point-max)))

(defun wikiedit--on-message (m)
  (let ((type (alist-get 'type m)))
    (cond
     ((equal type "clock") (setq wikiedit--offset (or (alist-get 'offset m) 0)))
     ((equal type "attachments") (setq wikiedit--attachments (alist-get 'attachments m)) (force-mode-line-update))
     ((equal type "edit")
      (wikiedit--flush)
      (if (not (equal (alist-get 'from m) (wikiedit--hash wikiedit--shadow)))
          (wikiedit--send-state)
        (let ((next (wikiedit--apply-changes wikiedit--shadow (alist-get 'changes m))))
          (if (not (equal (wikiedit--hash next) (alist-get 'to m)))
              (wikiedit--send-state)
            (dolist (ch (alist-get 'changes m))
              (wikiedit--apply-to-buffer ch))
            (setq wikiedit--shadow next
                  wikiedit--modified (wikiedit--to-local (alist-get 'modified m)))))))
     ((equal type "state") (wikiedit--resolve m))
     ((equal type "full")
      ;; 置き換える前に手元の分を送らない（送ると、編集画面とエディタの本文がずれる）。手元の分は控える
      (when (timerp wikiedit--send-timer) (cancel-timer wikiedit--send-timer))
      (let ((text (or (alist-get 'text m) "")))
        (unless (equal text (wikiedit--buffer-text))
          (wikiedit--keep-backup (wikiedit--buffer-text)))
        (wikiedit--replace-text text)
        (setq wikiedit--shadow text
              wikiedit--sent-state nil
              wikiedit--modified (wikiedit--to-local (alist-get 'modified m)))))
     ((equal type "cursor") (wikiedit--set-cursor (alist-get 'start m) (alist-get 'end m)))
     ((equal type "reload")
      ;; 編集画面が再読み込みする。このあと切れても、同じセッション ID で戻るのを待つ
      (setq wikiedit--expect-reload (wikiedit--now)))
     ((equal type "bye")
      (when wikiedit--proc (process-put wikiedit--proc :bye t))
      (wikiedit--close-buffer (current-buffer))))))

(defun wikiedit--resolve (m)
  (unless (equal (alist-get 'hash m) (wikiedit--hash wikiedit--shadow))
    ;; 新しいほうが full を送る。同じ時刻ならエディタ側を正とする
    (if (>= wikiedit--modified (wikiedit--to-local (alist-get 'modified m)))
        (wikiedit--send-full)
      (unless wikiedit--sent-state (wikiedit--send-state)))))

(defun wikiedit--send-full ()
  "いまのバッファの全文を full で送り、シャドウをそろえる。"
  (when (timerp wikiedit--send-timer) (cancel-timer wikiedit--send-timer))
  (let ((now (wikiedit--buffer-text)))
    (setq wikiedit--shadow now)
    (wikiedit--send wikiedit--proc
                    `((type . "full") (text . ,now) (hash . ,(wikiedit--hash now))
                      (modified . ,wikiedit--modified)))))

(defun wikiedit--send-state ()
  (setq wikiedit--sent-state t)
  (wikiedit--send wikiedit--proc
                         `((type . "state") (hash . ,(wikiedit--hash wikiedit--shadow))
                           (modified . ,wikiedit--modified))))

(defun wikiedit--keep-backup (text &optional what)
  (with-current-buffer (get-buffer-create (concat (buffer-name) " 控え"))
    (erase-buffer) (insert text))
  (message "wikiedit: %s（元の内容は「%s 控え」に残しました）"
           (or what "編集画面の内容が新しかったので置き換えました") (buffer-name)))

;;;; バッファへの書き込み

(defun wikiedit--replace-text (text)
  "バッファの本文を TEXT にする。前後で共通する部分を除いた1か所だけを書き換える。
`replace-buffer-contents' は違いを細かく調べるので、中身の違う長い本文（別のページへ
移ったとき）では何分もかかり、そのあいだ Emacs 全体が止まっていた。"
  (let* ((wikiedit--applying t) (inhibit-read-only t)
         (old (wikiedit--buffer-text)))
    (unless (equal old text)
      (pcase-let ((`(,s ,endb ,enda) (wikiedit--char-diff old text)))
        (save-excursion
          (goto-char (+ (point-min) s))
          (delete-region (point) (+ (point-min) endb))
          (insert (substring text s enda)))))))

(defun wikiedit--apply-to-buffer (ch)
  (let* ((text (wikiedit--buffer-text))
         (s (wikiedit--u16-to-index text (alist-get 'start ch)))
         (e (max s (wikiedit--u16-to-index text (alist-get 'end ch))))
         (wikiedit--applying t)
         (inhibit-read-only t))
    (save-excursion
      (goto-char (+ (point-min) s))
      (delete-region (point) (+ (point-min) e))
      (insert (or (alist-get 'text ch) "")))))

(defun wikiedit--set-cursor (start end)
  (let* ((text (wikiedit--buffer-text))
         (a (+ (point-min) (wikiedit--u16-to-index text start)))
         (b (+ (point-min) (wikiedit--u16-to-index text end))))
    (goto-char b)
    (if (= a b) (deactivate-mark) (push-mark a t t))
    (dolist (w (get-buffer-window-list (current-buffer) nil t)) (set-window-point w b))
    (setq wikiedit--last-cursor (cons start end))))

;;;; 手元の変更を送る

(defun wikiedit--after-change (_beg _end _len)
  (unless wikiedit--applying
    (setq wikiedit--modified (wikiedit--now))
    (unless (wikiedit--sendable-p)
      (unless wikiedit--unsent (setq wikiedit--unsent t) (force-mode-line-update)))
    (when (timerp wikiedit--send-timer) (cancel-timer wikiedit--send-timer))
    (let ((buf (current-buffer)))
      (setq wikiedit--send-timer
            (run-at-time 0.15 nil (lambda () (when (buffer-live-p buf)
                                               (with-current-buffer buf
                                                 (wikiedit--flush)
                                                 (wikiedit--send-cursor)))))))))

(defun wikiedit--flush ()
  (when (timerp wikiedit--send-timer) (cancel-timer wikiedit--send-timer))
  (let ((now (wikiedit--buffer-text)))
    (when (and (wikiedit--sendable-p) wikiedit--shadow (not (equal now wikiedit--shadow)))
      (pcase-let ((`(,s ,e ,ins) (wikiedit--diff wikiedit--shadow now)))
        (wikiedit--send wikiedit--proc
                               `((type . "edit") (from . ,(wikiedit--hash wikiedit--shadow))
                                 (to . ,(wikiedit--hash now))
                                 (changes . [((start . ,s) (end . ,e) (text . ,ins))])
                                 (modified . ,wikiedit--modified))))
      (setq wikiedit--shadow now))))

(defun wikiedit--cursor-u16 ()
  (let* ((text (wikiedit--buffer-text))
         (p (wikiedit--u16-length (substring text 0 (- (point) (point-min)))))
         (m (if (region-active-p)
                (wikiedit--u16-length (substring text 0 (- (mark) (point-min))))
              p)))
    (cons (min p m) (max p m))))

(defun wikiedit--send-cursor ()
  (when (wikiedit--sendable-p)
    (let ((c (wikiedit--cursor-u16)))
      (unless (equal c wikiedit--last-cursor)
        (setq wikiedit--last-cursor c)
        (wikiedit--send wikiedit--proc
                               `((type . "cursor") (start . ,(car c)) (end . ,(cdr c))))))))

(defun wikiedit--post-command ()
  (when (timerp wikiedit--cursor-timer) (cancel-timer wikiedit--cursor-timer))
  (let ((buf (current-buffer)))
    (setq wikiedit--cursor-timer
          (run-at-time 0.2 nil (lambda () (when (buffer-live-p buf)
                                            (with-current-buffer buf
                                              (when (equal (wikiedit--buffer-text) wikiedit--shadow)
                                                (wikiedit--send-cursor)))))))))

;;;; 添付ファイル

(defun wikiedit-insert-attachment (&optional copy)
  "ページの添付ファイルを選び、本文での書きかたをカーソルの位置に挿入する。
前置引数 COPY があれば、挿入せずに kill-ring にコピーする。"
  (interactive "P")
  (let ((items wikiedit--attachments))
    (if (null items)
        (message "wikiedit: このページに添付ファイルはありません")
      (let* ((names (mapcar (lambda (a) (alist-get 'name a)) items))
             (completion-extra-properties
              `(:annotation-function
                ,(lambda (name)
                   (let ((a (cl-find name items :key (lambda (x) (alist-get 'name x)) :test #'equal)))
                     (format "  %s %s" (or (alist-get 'kind a) "") (or (alist-get 'size a) ""))))))
             (name (completing-read (if copy "コピーする添付ファイル: " "挿入する添付ファイル: ") names nil t))
             (item (cl-find name items :key (lambda (x) (alist-get 'name x)) :test #'equal))
             (ref (or (alist-get 'ref item) name)))
        (if copy
            (progn (kill-new ref) (message "wikiedit: %s をコピーしました" ref))
          (insert ref))))))

;;;; 保存・閉じる

(defun wikiedit-save ()
  "Wiki の編集画面の保存を押す。"
  (interactive)
  (wikiedit--flush)
  (if wikiedit--proc
      (progn (wikiedit--send wikiedit--proc '((type . "save")))
             ;; 保存すると編集画面は再読み込みする。reload が届かなくても、通信の切断とは扱わない
             (setq wikiedit--expect-reload (wikiedit--now)))
    (message "wikiedit: 編集画面とつながっていません")))

(defun wikiedit-close ()
  "このバッファを閉じる。編集画面には「エディタ側で閉じました」と出る。"
  (interactive)
  (wikiedit--flush)
  (kill-buffer (current-buffer)))

(defun wikiedit--on-kill ()
  (when wikiedit--proc
    (process-put wikiedit--proc :bye t)
    (wikiedit--send wikiedit--proc '((type . "closed")))
    (delete-process wikiedit--proc))
  (when (timerp wikiedit--keep-timer) (cancel-timer wikiedit--keep-timer))
  (when wikiedit--session (remhash wikiedit--session wikiedit--sessions))
  (let ((frame wikiedit--frame))
    (when (and (frame-live-p frame) (cdr (frame-list)))
      (run-at-time 0 nil (lambda () (when (frame-live-p frame) (delete-frame frame)))))))

(defun wikiedit--close-buffer (buf)
  (when (buffer-live-p buf)
    (with-current-buffer buf
      (when wikiedit--proc
        (let ((proc wikiedit--proc))
          (setq wikiedit--proc nil)
          (process-put proc :bye t)
          (delete-process proc))))
    (kill-buffer buf)))

(defvar wikiedit-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-c") #'wikiedit-close)
    (define-key map (kbd "C-c C-a") #'wikiedit-insert-attachment)
    (define-key map [remap save-buffer] #'wikiedit-save)
    map))

(define-minor-mode wikiedit-mode
  "wikiSystem の編集画面と同期しているバッファ。"
  :lighter (:eval (wikiedit--lighter))
  :keymap wikiedit-mode-map
  (if wikiedit-mode
      (progn
        (add-hook 'after-change-functions #'wikiedit--after-change nil t)
        (add-hook 'post-command-hook #'wikiedit--post-command nil t)
        (add-hook 'kill-buffer-hook #'wikiedit--on-kill nil t))
    (remove-hook 'after-change-functions #'wikiedit--after-change t)
    (remove-hook 'post-command-hook #'wikiedit--post-command t)
    (remove-hook 'kill-buffer-hook #'wikiedit--on-kill t)))

;; メジャーモードを替えると、バッファの変数が消える。同期の状態は残す
(dolist (v '(wikiedit--proc wikiedit--session wikiedit--page
             wikiedit--shadow wikiedit--modified wikiedit--offset
             wikiedit--sent-state wikiedit--keep-timer wikiedit--frame
             wikiedit--attachments wikiedit--link wikiedit--last-recv wikiedit--unsent
             wikiedit--expect-reload))
  (put v 'permanent-local t))
(put 'wikiedit--after-change 'permanent-local-hook t)
(put 'wikiedit--post-command 'permanent-local-hook t)
(put 'wikiedit--on-kill 'permanent-local-hook t)

;;;; 起動・停止

;;;###autoload
(defun wikiedit-start ()
  "編集画面からの接続を待ち受ける。
同じポートでほかの Emacs が待ち受けていれば、`wikiedit-takeover-interval' 秒ごとに
確かめ、いなくなったら引き継ぐ。"
  (interactive)
  (wikiedit--load-associated)
  (unless (timerp wikiedit--stale-timer)
    (setq wikiedit--stale-timer (run-at-time 10 10 #'wikiedit--check-stale)))
  (unless (process-live-p wikiedit--server)
    (if (wikiedit--listen)
        (message "wikiedit: %d で待ち受けています" wikiedit-port)
      (message "wikiedit: %d はほかの Emacs が待ち受けています。%d 秒ごとに確かめ、いなくなったら引き継ぎます"
               wikiedit-port wikiedit-takeover-interval)
      (wikiedit--watch))))

(defun wikiedit--listen ()
  "待ち受けを始める。ポートがふさがっていれば nil。"
  (condition-case nil
      (progn
        (setq wikiedit--server
              (make-network-process
               :name "wikiedit" :server t :host 'local :service wikiedit-port
               :family 'ipv4 :coding 'binary :noquery t
               :filter #'wikiedit--filter :sentinel #'wikiedit--sentinel))
        t)
    (file-error nil)))

(defun wikiedit--watch ()
  (unless (timerp wikiedit--watch-timer)
    (setq wikiedit--watch-timer
          (run-at-time wikiedit-takeover-interval wikiedit-takeover-interval
                       #'wikiedit--try-takeover))))

(defun wikiedit--try-takeover ()
  (when (wikiedit--listen)
    (cancel-timer wikiedit--watch-timer)
    (setq wikiedit--watch-timer nil)
    (message "wikiedit: 待ち受けていた Emacs がいなくなったので、%d を引き継ぎました"
             wikiedit-port)))

(defun wikiedit-stop ()
  "待ち受けをやめ、同期しているバッファを閉じる。"
  (interactive)
  (when (timerp wikiedit--watch-timer) (cancel-timer wikiedit--watch-timer))
  (setq wikiedit--watch-timer nil)
  (when (timerp wikiedit--stale-timer) (cancel-timer wikiedit--stale-timer))
  (setq wikiedit--stale-timer nil)
  (when (process-live-p wikiedit--server) (delete-process wikiedit--server))
  (setq wikiedit--server nil)
  (maphash (lambda (_ buf) (wikiedit--close-buffer buf)) wikiedit--sessions)
  (clrhash wikiedit--sessions))

(provide 'wikiedit)
;;; wikiedit.el ends here
