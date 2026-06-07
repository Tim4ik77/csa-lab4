(defconst IO_OUT 8)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun main ()
  (begin
    (putc 'H')
    (putc 'e')
    (putc 'l')
    (putc 'l')
    (putc 'o')
    (putc '\n')))
