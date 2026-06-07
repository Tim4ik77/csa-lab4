(defconst IO_OUT 8)

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

(defun fib (n)
  (if (< n 2)
    n
    (+ (fib (- n 1)) (fib (- n 2)))))

(defun main ()
  (begin
    (print_uint (fib 6))
    (putc '\n')))
