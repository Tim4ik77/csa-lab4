(defconst IO_IN 0)
(defconst IO_STATUS 4)
(defconst IO_OUT 8)

(defun main ()
  (while 1 0))

(on-input
  (begin
    (mem-set IO_OUT (mem-get IO_IN))
    (mem-set IO_STATUS 0)))
