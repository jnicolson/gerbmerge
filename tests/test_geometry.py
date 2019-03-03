import pytest

from gerbmerge.geometry import segmentXbox, intersectExtents, isRect1InRect2

llpt = (1000,1000)
urpt = (5000,5000)

# A segment that cuts across the box and intersects in corners
def test_segment1():
  assert segmentXbox((0,0), (6000,6000), llpt, urpt) == [(1000,1000), (5000,5000)]  # Two valid corners
  assert segmentXbox((0,6000), (6000,0), llpt, urpt) == [(1000,5000), (5000,1000)]  # Two valid corners
  assert segmentXbox((500,500), (2500, 2500), llpt, urpt) == [(1000,1000)]          # One valid corner
  assert segmentXbox((2500,2500), (5500, 5500), llpt, urpt) == [(5000,5000)]        # One valid corner

# Segments collinear with box sides
def test_segment2():
  assert segmentXbox((1000,0),    (1000,6000), llpt, urpt) == []    # Box side contained in segment
  assert segmentXbox((1000,0),    (1000,3000), llpt, urpt) == []    # Box side partially overlaps segment
  assert segmentXbox((1000,2000), (1000,4000), llpt, urpt) == []    # Segment contained in box side

# Segments fully contained within box
def test_segment3():
  assert segmentXbox((1500,2000), (2000,2500), llpt, urpt) == []

# Segments with points on box sides
def test_segment4():
  assert segmentXbox((2500,1000), (2700,1200), llpt, urpt) == [(2500,1000)]   # One point on box side
  assert segmentXbox((2500,1000), (2700,5000), llpt, urpt) == [(2500,1000), (2700,5000)]   # Two points on box sides

# Segment intersects box at one point
def test_segment5():
  assert segmentXbox((3500,5500), (3000, 2500), llpt, urpt) == [(3417, 5000)]  # First point outside
  assert segmentXbox((3500,1500), (3000, 6500), llpt, urpt) == [(3150, 5000)]  # Second point outside

# Segment intersects box at two points, not corners
def test_segment6():
  assert segmentXbox((500,3000), (1500,500), llpt, urpt) == [(1000,1750), (1300,1000)]
  assert segmentXbox((2500,300), (5500,3500), llpt, urpt) == [(3156,1000), (5000,2967)]
  assert segmentXbox((5200,1200), (2000,6000), llpt, urpt) == [(2667,5000), (5000, 1500)]
  assert segmentXbox((3200,5200), (-10, 1200), llpt, urpt) == [(1000, 2459), (3040, 5000)]

  assert segmentXbox((500,2000), (5500, 2000), llpt, urpt) == [(1000,2000), (5000, 2000)]
  assert segmentXbox((5200,1250), (-200, 4800), llpt, urpt) == [(1000, 4011), (5000, 1381)]

  assert segmentXbox((1300,200), (1300, 5200), llpt, urpt) == [(1300, 1000), (1300, 5000)]
  assert segmentXbox((1200,200), (1300, 5200), llpt, urpt) == [(1216, 1000), (1296, 5000)]

  assert intersectExtents( (100,100,500,500), (500,500,900,900) ) == None
  assert intersectExtents( (100,100,500,500), (400,400,900,900) ) == (400,400,500,500)
  assert intersectExtents( (100,100,500,500), (200,0,600,300) ) == (200,100,500,300)
  assert intersectExtents( (100,100,500,500), (200,0,300,600) ) == (200,100,300,500)

  assert intersectExtents( (100,100,500,500), (0,600,50,550) ) == None
  assert intersectExtents( (100,100,500,500), (0,600,600,-10) ) == (100,100,500,500)
  assert intersectExtents( (100,100,500,500), (0,600,600,200) ) == (100,200,500,500)
  assert intersectExtents( (100,100,500,500), (0,600,300,300) ) == (100,300,300,500)

  assert isRect1InRect2( (100,100,500,500), (0,600,50,550) )  == False
  assert isRect1InRect2( (100,100,500,500), (0,600,600,-10) ) == True
  assert isRect1InRect2( (100,100,500,500), (0,600,600,200) ) == False
  assert isRect1InRect2( (100,100,500,500), (0,600,300,300) ) == False
  assert isRect1InRect2( (100,100,500,500), (0,0,500,500) )   == True