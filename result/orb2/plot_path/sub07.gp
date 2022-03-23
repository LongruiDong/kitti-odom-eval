set term postscript eps enhanced color
set output "07.eps"
set size ratio -1
set xrange [-206:23]
set yrange [-99:131]
set xlabel "x [m]"
set ylabel "z [m]"
plot "sub07.txt" using 1:2 lc rgb "#FF0000" title 'Ground Truth' w lines,"sub07.txt" using 3:4 lc rgb "#0000FF" title 'Visual Odometry' w lines,"< head -1 sub07.txt" using 1:2 lc rgb "#000000" pt 4 ps 1 lw 2 title 'Sequence Start' w points
