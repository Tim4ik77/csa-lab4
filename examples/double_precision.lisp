(defconst IO_OUT 8)
(defconst BASE 1000000)

(defvar a_hi 4000)
(defvar a_lo 0)
(defvar b_hi 4000)
(defvar b_lo 0)
(defvar r_hi 0)
(defvar r_lo 0)

(defun putc (ch)
  (mem-set IO_OUT ch))

(defun print_uint_rec (x)
  (if (< x 10)
    (putc (+ x '0'))
    (begin
      (print_uint_rec (/ x 10))
      (putc (+ (mod x 10) '0')))))

(defun print_uint (x)
  (if (= x 0)
    (putc '0')
    (print_uint_rec x)))

(defun print_lo6 (x)
  (begin
    (if (< x 100000) (putc '0') 0)
    (if (< x 10000) (putc '0') 0)
    (if (< x 1000) (putc '0') 0)
    (if (< x 100) (putc '0') 0)
    (if (< x 10) (putc '0') 0)
    (print_uint x)))

(defun add_u64 ()
  (begin
    (setq r_lo (+ a_lo b_lo))
    (setq r_hi (+ a_hi b_hi))
    (if (>= r_lo BASE)
      (begin
        (setq r_lo (- r_lo BASE))
        (setq r_hi (+ r_hi 1)))
      0)))

(defun main ()
  (begin
    (add_u64)
    (print_uint r_hi)
    (print_lo6 r_lo)
    (putc '\n')))
