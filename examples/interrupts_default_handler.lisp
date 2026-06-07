(defconst IO_STATUS 4)
(defconst IO_OUT 8)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun main ()
  (begin
    (while (= (mem-get IO_STATUS) 0) 0)
    (putc 'D')
    (putc '\n')))
