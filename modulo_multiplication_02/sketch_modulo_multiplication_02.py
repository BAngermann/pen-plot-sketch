import vsketch
import math

def crossProduct2d(p1x,p1y, p2x,p2y) :
    return p1x * p2y - p1y * p2x

def dist(p1,p2):
   return math.sqrt( (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def minDist(ref,points):
   dists = [dist(ref,x) for x in points ]
   dists = list(filter(lambda a: a > 1e-10, dists))
   return min(dists)

# assume no points are equal and line segments cannot lie on the same line
def intersect(line1,line2) :
  if line1==line2:
     return [float('inf'),float('inf')]  
  x1 = line1[0]
  y1 = line1[1]
  x2 = line1[2]
  y2 = line1[3]

  x3 = line2[0]
  y3 = line2[1]
  x4 = line2[2]
  y4 = line2[3]

  if (x1==x3) and (y1==y3):
    return [float('inf'),float('inf')]
  if (x1==x4) and (y1==y4):
    return [float('inf'),float('inf')]
  if (x2==x3) and (y2==y3):
    return [float('inf'),float('inf')]
  if (x2==x4) and (y2==y4):
    return [float('inf'),float('inf')]

  rx = x2-x1
  ry = y2-y1
  sx = x4-x3
  sy = y4-y3

  denominator = crossProduct2d(rx,ry, sx,sy)

  if (denominator == 0) :
    return [float('inf'),float('inf')]

  qpx = x3-x1
  qpy = y3-y1
  u = crossProduct2d(qpx,qpy, rx,ry) / denominator
  t = crossProduct2d(qpx,qpy, sx,sy) / denominator

  if ((t >= 0) and (t <= 1) and (u >= 0) and (u <= 1)) :
    return[x1+t*rx,y1+t*ry]
  else :
    return [float('inf'),float('inf')]
  



class ModuloMultiplication01Sketch(vsketch.SketchClass):
    r = vsketch.Param(4.0)
    multiplier = vsketch.Param(8)
    n = vsketch.Param(10)

    def draw(self, vsk: vsketch.Vsketch) -> None:
        vsk.size("10cm","10cm", landscape=False)
        vsk.scale("cm")
        twopi = 6.28318530718
        tpn = twopi/self.n

        lines = [ [-self.r * math.cos(i*tpn),
                     self.r * math.sin(i * tpn),
                     -self.r * math.cos(((i * self.multiplier) % self.n) * tpn),
                     self.r * math.sin(((i * self.multiplier) % self.n) * tpn)] for i in range(self.n)]
        
 
        intersections = [intersect(l1,l2) for l1 in lines for l2 in lines]
        intersections[:] = [x for x in intersections if x[0] < float('inf')]
        intersections = [ii for n,ii in enumerate(intersections) if ii not in intersections[:n]]
        
        nn = [minDist(p,intersections) for p in intersections]

        for i,d in zip(intersections,nn):
           vsk.circle(i[0], i[1], d)
        vsk.text(text = f'n={self.n}',x=-self.r,y=self.r,size = "0.25",mode = "transform",font = "futural")
        vsk.text(text = f'x={self.multiplier}',x=self.r,y=self.r,size = "0.25",mode = "transform",font = "futural",align="right")


    def finalize(self, vsk: vsketch.Vsketch) -> None:
        vsk.vpype("linemerge linesimplify reloop linesort")


if __name__ == "__main__":
    ModuloMultiplication01Sketch.display()
