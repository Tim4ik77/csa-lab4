(defconst IO_IN 0)
(defconst IO_STATUS 4)
(defconst IO_OUT 8)

(defvar done 0)
(defvar pos 0)
(defbuffer NAME 16)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun puts (s)
  (while (!= (mem-get s) 0)
    (begin
      (putc (mem-get s))
      (setq s (+ s 4)))))

(defun name_addr (idx)
  (+ NAME (* idx 4)))

(defun main ()
  (begin
    (puts "What is your name?\n")
    (while (= done 0) 0)
    (puts "Hello, ")
    (puts NAME)
    (putc '!')
    (putc '\n')))

(on-input
  (begin
    (if (= (mem-get IO_IN) '\n')
      (begin
        (mem-set (name_addr pos) 0)
        (setq done 1))
      (begin
        (mem-set (name_addr pos) (mem-get IO_IN))
        (setq pos (+ pos 1))))
    (mem-set IO_STATUS 0)))
