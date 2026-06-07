(defconst IO_OUT 8)

(defbuffer ARR 3)
(defvar i 0)
(defvar j 0)
(defvar tmp 0)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun addr (idx)
  (+ ARR (* idx 4)))

(defun swap (a b)
  (begin
    (setq tmp (mem-get (addr a)))
    (mem-set (addr a) (mem-get (addr b)))
    (mem-set (addr b) tmp)))

(defun print_digit (n)
  (putc (+ n '0')))

(defun main ()
  (begin
    (mem-set (addr 0) 3)
    (mem-set (addr 1) 1)
    (mem-set (addr 2) 2)
    (setq i 0)
    (while (< i 3)
      (begin
        (setq j 0)
        (while (< j 2)
          (begin
            (if (> (mem-get (addr j)) (mem-get (addr (+ j 1))))
              (swap j (+ j 1))
              0)
            (setq j (+ j 1))))
        (setq i (+ i 1))))
    (print_digit (mem-get (addr 0)))
    (print_digit (mem-get (addr 1)))
    (print_digit (mem-get (addr 2)))
    (putc '\n')))
